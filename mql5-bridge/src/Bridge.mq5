//+------------------------------------------------------------------+
//| Bridge.mq5 - READ-ONLY telemetry bridge for abc-bot-paper-trader|
//+------------------------------------------------------------------+
//| READ-ONLY TELEMETRY BRIDGE                                       |
//|                                                                    |
//| Lifecycle: INIT -> VERIFY TERMINAL -> VERIFY SYMBOL ->            |
//|   START READ-ONLY COLLECTION -> TICK COLLECTION ->                |
//|   TRADE TRANSACTION TELEMETRY -> POSITION/ORDER SNAPSHOT ->       |
//|   HEALTH HEARTBEAT -> DEINIT.                                     |
//|                                                                    |
//| This bridge is STRICTLY READ-ONLY. It never places, modifies,     |
//| or deletes orders, and it performs no execution-capable call.     |
//| It observes market ticks, terminal trade transactions, and        |
//| position/order state, and appends raw canonical-compatible JSONL  |
//| telemetry (see Events/EventBuilder.mqh and docs/ARCHITECTURE.md). |
//+------------------------------------------------------------------+
#property strict
#property description "abc-bot-paper-trader read-only MQL5 telemetry bridge"
#property version   "1.00"

#include "Config.mqh"
#include "Export/JsonExporter.mqh"
#include "Events/EventBuilder.mqh"
#include "Health/HealthMonitor.mqh"

CJsonExporter   g_exporter;
CHealthMonitor  g_health;
MqlTick         g_lastTick;
int             g_writesSinceFlush = 0;
bool            g_wasConnected = false;
bool            g_disconnectedReported = false;

//------------------------------------------------------------------+
// Helpers (read-only)                                              |
//------------------------------------------------------------------+

// Broker state enum -> contract-compatible string (verbatim state).
string OrderStateName(const long state)
{
   switch((ENUM_ORDER_STATE)state)
   {
      case ORDER_STATE_STARTED:         return "STARTED";
      case ORDER_STATE_PLACED:          return "PLACED";
      case ORDER_STATE_CANCELED:        return "CANCELED";
      case ORDER_STATE_PARTIAL:         return "PARTIAL";
      case ORDER_STATE_FILLED:          return "FILLED";
      case ORDER_STATE_REJECTED:        return "REJECTED";
      case ORDER_STATE_EXPIRED:         return "EXPIRED";
      case ORDER_STATE_REQUEST_ADD:     return "REQUEST_ADD";
      case ORDER_STATE_REQUEST_MODIFY:  return "REQUEST_MODIFY";
      case ORDER_STATE_REQUEST_CANCEL:  return "REQUEST_CANCEL";
      default:                          return "UNKNOWN";
   }
}

// Deal direction -> contract-compatible string.
string DealDirectionName(const long dealType)
{
   if((ENUM_DEAL_TYPE)dealType == DEAL_TYPE_BUY)
      return "BUY";
   if((ENUM_DEAL_TYPE)dealType == DEAL_TYPE_SELL)
      return "SELL";
   return "UNKNOWN";
}

// Pending order type -> readable snapshot evidence string.
string OrderTypeName(const long orderType)
{
   switch((ENUM_ORDER_TYPE)orderType)
   {
      case ORDER_TYPE_BUY_LIMIT:       return "BUY_LIMIT";
      case ORDER_TYPE_SELL_LIMIT:      return "SELL_LIMIT";
      case ORDER_TYPE_BUY_STOP:        return "BUY_STOP";
      case ORDER_TYPE_SELL_STOP:       return "SELL_STOP";
      case ORDER_TYPE_BUY_STOP_LIMIT:  return "BUY_STOP_LIMIT";
      case ORDER_TYPE_SELL_STOP_LIMIT: return "SELL_STOP_LIMIT";
      default:                         return "UNKNOWN";
   }
}

// End-Of-Life deal entry markers (read-only filter, never an action).
bool IsClosingEntry(const long entry)
{
   return (ENUM_DEAL_ENTRY)entry == DEAL_ENTRY_OUT
          || (ENUM_DEAL_ENTRY)entry == DEAL_ENTRY_OUT_BY;
}

bool IsOpeningEntry(const long entry)
{
   return (ENUM_DEAL_ENTRY)entry == DEAL_ENTRY_IN
          || (ENUM_DEAL_ENTRY)entry == DEAL_ENTRY_INOUT;
}

bool IsOpeningAndClosingEntry(const long entry)
{
   return (ENUM_DEAL_ENTRY)entry == DEAL_ENTRY_INOUT;
}

// Approximate execution slippage from the current market (>= 0).
// The bridge does not have access to the broker's request price for
// market orders; this is raw evidence, and the collector is the
// authority for canonical derivation (documented limitation).
double ApproximateSlippage(const string direction, const double fillPrice)
{
   double bid = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
   if(direction == "BUY")
      return MathMax(fillPrice - ask, 0.0);
   if(direction == "SELL")
      return MathMax(bid - fillPrice, 0.0);
   return 0.0;
}

//------------------------------------------------------------------+
// Emission path (append-only JSONL)                                 |
//------------------------------------------------------------------+
bool EmitLine(const string line)
{
   if(line == "")
      return false;
   if(g_exporter.AppendLine(line))
   {
      g_health.OnWrite(true);
      g_writesSinceFlush++;
      if(g_writesSinceFlush >= InpFlushLines)
      {
         g_exporter.Flush();
         g_writesSinceFlush = 0;
      }
      return true;
   }
   g_health.OnError();
   return false;
}

//------------------------------------------------------------------+
// OnTradeTransaction: telemetry ONLY. No action is ever taken.      |
//------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   string tsBridge = E_IsoTime(TimeTradeServer());
   if(trans.type == TRADE_TRANSACTION_ORDER_ADD
      || trans.type == TRADE_TRANSACTION_ORDER_UPDATE)
   {
      if(!HistoryOrderSelect(trans.order))
         return;
      long ticket = HistoryOrderGetInteger(trans.order, ORDER_TICKET);
      long state  = HistoryOrderGetInteger(trans.order, ORDER_STATE);
      datetime orderTime = (datetime)HistoryOrderGetInteger(trans.order, ORDER_TIME_SETUP);
      if(ticket <= 0)
         return;
      EmitLine(E_BuildOrderAckLine(InpSymbol, IntegerToString(ticket),
                                   OrderStateName(state), orderTime, tsBridge));
   }

   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      if(!HistoryDealSelect(trans.deal))
         return;
      long dealTicket = HistoryDealGetInteger(trans.deal, DEAL_TICKET);
      long orderTicket = HistoryDealGetInteger(trans.deal, DEAL_ORDER);
      long positionId = HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
      long dealType = HistoryDealGetInteger(trans.deal, DEAL_TYPE);
      long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
      if(dealTicket <= 0)
         return;

      string direction = DealDirectionName(dealType);
      double price = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
      double volume = HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
      datetime dealTime = (datetime)HistoryDealGetInteger(trans.deal, DEAL_TIME);

      if(orderTicket > 0)
      {
         EmitLine(E_BuildOrderFillLine(InpSymbol, IntegerToString(orderTicket),
                                       IntegerToString(dealTicket), price, volume,
                                       ApproximateSlippage(direction, price),
                                       dealTime, tsBridge));
      }

      if(IsOpeningEntry(entry) && positionId > 0)
      {
         EmitLine(E_BuildPositionOpenedLine(InpSymbol, IntegerToString(positionId),
                                            direction, volume, price, dealTime, tsBridge));
      }

      if(IsClosingEntry(entry))
      {
         double profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
         double commission = HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
         double swap = HistoryDealGetDouble(trans.deal, DEAL_SWAP);
         double transactionCost = -(commission + swap);
         double netPnl = profit + commission + swap;
         string comment = HistoryDealGetString(trans.deal, DEAL_COMMENT);
         string exitReason = (comment != "") ? comment : "UNKNOWN";
         EmitLine(E_BuildPositionClosedLine(InpSymbol, IntegerToString(positionId),
                                            price, volume, dealTime, profit,
                                            transactionCost, netPnl, exitReason, tsBridge));
      }
   }
}

//------------------------------------------------------------------+
// OnTick: tick collection (never deduplicated)                     |
//------------------------------------------------------------------+
void OnTick()
{
   if(!SymbolInfoTick(InpSymbol, g_lastTick))
   {
      g_health.SetSymbolAvailable(false);
      return;
   }
   g_health.SetSymbolAvailable(true);
   g_health.OnTickSeen(g_lastTick);
   string tsBridge = E_IsoTime(TimeTradeServer());
   if(!EmitLine(E_BuildTickLine(InpSymbol, g_lastTick, tsBridge)))
   {
      // Never dropped silently: bounded reopen attempts happen inside
      // the exporter; we additionally log locally for the operator.
      Print("mql5-bridge: tick write failed (error_count=",
            IntegerToString(g_health.ErrorCount()), ")");
   }
}

//------------------------------------------------------------------+
// OnTimer: heartbeat + position/order snapshots + POSITION_UPDATED |
//------------------------------------------------------------------+
void OnTimer()
{
   static int timerCount = 0;
   timerCount++;

   g_health.SetTerminalConnected(TerminalInfoInteger(TERMINAL_CONNECTED) > 0);

   // Terminal disconnected: report once per episode, recover silently.
   if(!g_health.TerminalConnected())
   {
      if(!g_disconnectedReported && timerCount % InpHeartbeatSec == 0)
      {
         g_disconnectedReported = true;
         EmitLine(E_BuildTimeoutLine("TERMINAL_DISCONNECTED", "WARN",
                                     "terminal connection lost; bridge is read-only "
                                     "and will resume automatically when reconnected",
                                     E_IsoTime(TimeCurrent())));
      }
   }
   else if(g_disconnectedReported)
   {
      g_disconnectedReported = false;
      EmitLine(E_BuildErrorLine("TERMINAL_RECONNECTED", "INFO",
                                "terminal connection restored", E_IsoTime(TimeCurrent())));
   }

   // POSITION_UPDATED telemetry (periodic, per open position).
   if(timerCount % InpPositionUpdateSec == 0)
   {
      string tsBridge = E_IsoTime(TimeTradeServer());
      for(int i = 0; i < PositionsTotal(); i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0 || !PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != InpSymbol)
            continue;
         string posId = IntegerToString(ticket);
         string direction = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY
                            ? "BUY" : "SELL";
         double currentPrice = (direction == "BUY")
                               ? SymbolInfoDouble(InpSymbol, SYMBOL_BID)
                               : SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
         double runningPnl = PositionGetDouble(POSITION_PROFIT);
         // POSITION_COMMISSION is deprecated in current MQL5 builds; the
         // bridge approximates net with profit + swap and leaves the
         // commission to the collector (normalization authority).
         double runningNet = runningPnl + PositionGetDouble(POSITION_SWAP);
         double spread = SymbolInfoDouble(InpSymbol, SYMBOL_ASK)
                         - SymbolInfoDouble(InpSymbol, SYMBOL_BID);
         EmitLine(E_BuildPositionUpdatedLine(InpSymbol, posId, direction, currentPrice,
                                             runningPnl, runningNet, spread, tsBridge));
      }
   }

   // Position/order snapshots (read-only reconciliation evidence).
   if(timerCount % InpSnapshotSec == 0)
   {
      string tsBridge = E_IsoTime(TimeTradeServer());
      string positionsBody = "";
      int total = 0;
      for(int i = 0; i < PositionsTotal(); i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0 || !PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != InpSymbol)
            continue;
         if(positionsBody != "")
            positionsBody += ",";
         string direction = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY
                            ? "BUY" : "SELL";
         double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         double volume = PositionGetDouble(POSITION_VOLUME);
         double currentPrice = (direction == "BUY")
                               ? SymbolInfoDouble(InpSymbol, SYMBOL_BID)
                               : SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
         datetime openTs = (datetime)PositionGetInteger(POSITION_TIME);
         positionsBody += E_PositionSnapshotEntry(
            InpSymbol, IntegerToString(ticket), direction, volume, openPrice,
            currentPrice, E_IsoTime(openTs), "OPEN");
         ++total;
      }
      if(total > 0)
         EmitLine(E_BuildPositionSnapshotLine(InpSymbol, positionsBody, tsBridge));

      string ordersBody = "";
      int orderCount = 0;
      for(int i = 0; i < OrdersTotal(); i++)
      {
         ulong ticket = OrderGetTicket(i);
         if(ticket == 0)
            continue;
         if(OrderGetString(ORDER_SYMBOL) != InpSymbol)
            continue;
         if(ordersBody != "")
            ordersBody += ",";
         ordersBody += E_OrderSnapshotEntry(
            IntegerToString(ticket),
            OrderTypeName(OrderGetInteger(ORDER_TYPE)),
            OrderStateName(OrderGetInteger(ORDER_STATE)),
            OrderGetDouble(ORDER_PRICE_OPEN),
            OrderGetDouble(ORDER_VOLUME_CURRENT),
            E_IsoTime((datetime)OrderGetInteger(ORDER_TIME_SETUP)));
         ++orderCount;
      }
      if(orderCount > 0)
         EmitLine(E_BuildOrderSnapshotLine(InpSymbol, ordersBody, tsBridge));
   }

   // Heartbeat.
   if(timerCount % InpHeartbeatSec == 0)
   {
      string lastTick = (g_health.LastTickTime() > 0)
                        ? E_IsoTime(g_health.LastTickTime()) : "";
      string lastWrite = (g_health.LastWriteOkTime() > 0)
                         ? E_IsoTime(g_health.LastWriteOkTime()) : "";
      string status = g_health.TerminalConnected() ? "RUNNING" : "DEGRADED";
      int positionCount = PositionsTotal();
      int orderCount = OrdersTotal();
      EmitLine(E_BuildHeartbeatLine(status, g_health.TerminalConnected(),
                                    g_health.SymbolAvailable(), lastTick,
                                    g_exporter.IsOpen(), lastWrite,
                                    g_health.ErrorCount(), g_health.TickCount(),
                                    g_health.WriteCount(), positionCount,
                                    orderCount, E_IsoTime(TimeTradeServer())));
      g_exporter.Flush();
   }
}

//------------------------------------------------------------------+
// Lifecycle                                                         |
//------------------------------------------------------------------+
int OnInit()
{
   string tsBridge = E_IsoTime(TimeTradeServer());
   g_health.SetTerminalConnected(TerminalInfoInteger(TERMINAL_CONNECTED) > 0);

   // VERIFY TERMINAL (read-only availability check).
   if(!g_health.TerminalConnected())
   {
      Print("mql5-bridge: terminal not connected; starting in degraded mode");
   }

   // VERIFY SYMBOL: select for tick access + capability probe.
   bool symbolOk = SymbolSelect(InpSymbol, true);
   if(symbolOk)
   {
      MqlTick probe;
      symbolOk = SymbolInfoTick(InpSymbol, probe);
   }
   if(!symbolOk)
   {
      Print("mql5-bridge: symbol unavailable (", InpSymbol, "); "
            "entering degraded read-only mode with heartbeat only");
   }
   g_health.SetSymbolAvailable(symbolOk);

   // VERIFY ACCOUNT CONTEXT (read-only; no order capability touched).
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(balance < 0.0)
      Print("mql5-bridge: account context unreadable");
   string server = AccountInfoString(ACCOUNT_SERVER);

   // INITIALIZE EXPORTER.
   if(!g_exporter.Open(InpEventFile, InpMaxReopenAttempts))
   {
      Print("mql5-bridge: cannot open event file (", InpEventFile, "); "
            "starting in degraded mode");
   }

   // EMIT HEALTH/START EVENT.
   EmitLine(E_BuildHeartbeatLine("STARTED", g_health.TerminalConnected(),
                                 g_health.SymbolAvailable(), "",
                                 g_exporter.IsOpen(), "",
                                 g_health.ErrorCount(), 0, 0,
                                 PositionsTotal(), OrdersTotal(),
                                 tsBridge));
   g_exporter.Flush();

   EventSetTimer(1);
   Print("mql5-bridge: started read-only telemetry for ", InpSymbol,
         " (server=", server, ", output=", InpEventFile, ")");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   g_exporter.Flush();
   string tsBridge = E_IsoTime(TimeCurrent());
   // Best-effort final health line (write may already be impossible).
   EmitLine(E_BuildHeartbeatLine("STOPPED", g_health.TerminalConnected(),
                                 g_health.SymbolAvailable(), "",
                                 g_exporter.IsOpen(), "",
                                 g_health.ErrorCount(), g_health.TickCount(),
                                 g_health.WriteCount(), PositionsTotal(),
                                 OrdersTotal(), tsBridge));
   g_exporter.Flush();
   g_exporter.Close();
   Print("mql5-bridge: stopped (reason=", IntegerToString(reason), ")");
}