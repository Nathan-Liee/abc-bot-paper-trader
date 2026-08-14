//+------------------------------------------------------------------+
//| EventBuilder.mqh - raw canonical-compatible event lines          |
//+------------------------------------------------------------------+
//| READ-ONLY TELEMETRY BRIDGE                                       |
//|                                                                    |
//| The bridge produces RAW event input, not full canonical           |
//| envelopes: payload field names and types mirror                  |
//| shared/schemas/canonical-event.schema.json exactly, but no        |
//| event_id / correlation_id / trade_id / checksum are assigned      |
//| here. The collector owns event identity (section 13) and          |
//| canonicalization + checksum (section 14 of the task brief).       |
//|                                                                    |
//| Event types produced by this bridge:                              |
//|   TICK_RECEIVED (always)                                          |
//|   ORDER_ACKNOWLEDGED / ORDER_FILLED      (from trade transactions)|
//|   POSITION_OPENED / POSITION_UPDATED / POSITION_CLOSED            |
//|   ERROR / TIMEOUT                        (bridge failures)        |
//|   POSITION_SNAPSHOT / ORDER_SNAPSHOT     (read-only evidence for  |
//|                                           collector reconciliation)|
//|   HEARTBEAT                              (health telemetry)       |
//|                                                                    |
//| NEVER produced here (collector/system-owned): TRIGGER_DETECTED,   |
//| CONTEXT_BUILT, AI_REQUEST, AI_RESPONSE, RISK_GATE,                |
//| NET_PROFIT_POSITIVE, EXIT_SUBMITTED.                              |
//+------------------------------------------------------------------+
#property strict

// Line format: {"event_type":"<TYPE>","source":"mql5","ts_bridge":"<ISO>","payload":{...}}
//   ts_bridge      : bridge observation time, broker server time (ISO 8601 UTC, seconds).
//                    The bridge never fabricates sub-second precision it does not have.
//   No envelope fields (event_id/checksum/...) - collector fills them.

string E_JsonEscape(const string input)
{
   string out = "";
   int len = StringLen(input);
   for(int i = 0; i < len; i++)
   {
      ushort code = StringGetCharacter(input, i);
      if(code == '"')
         out += "\\\"";
      else if(code == '\\')
         out += "\\\\";
      else if(code == '\n')
         out += "\\n";
      else if(code == '\r')
         out += "\\r";
      else if(code == '\t')
         out += "\\t";
      else if(code < 0x20)
         out += StringFormat("\\u%04x", code);
      else if(code >= 0x7F)
         out += StringFormat("\\u%04x", code); // keep output strictly ASCII (UTF-8 safe)
      else
         out += ShortToString(code);
   }
   return out;
}

string E_FormatNumber(const double value)
{
   string s = DoubleToString(value, 8);
   // Trim trailing zeros, keep at least one decimal digit.
   int dot = StringFind(s, ".");
   if(dot >= 0)
   {
      int i = StringLen(s) - 1;
      while(i > dot && StringGetCharacter(s, i) == '0')
         i--;
      if(i == dot)
         i++;
      s = StringSubstr(s, 0, i + 1);
   }
   if(StringLen(s) == 0)
      s = "0";
   return s;
}

// ISO 8601 UTC seconds; ms > 0 appends real millisecond precision.
// The caller only passes milliseconds that genuinely came from MQL5.
string E_IsoTime(const datetime t, const int ms = 0)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   string s = StringFormat("%04d-%02d-%02dT%02d:%02d:%02d",
                           dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
   if(ms > 0)
      s += StringFormat(".%03dZ", ms);
   else
      s += "Z";
   return s;
}

string E_Bool(const bool value)
{
   return value ? "true" : "false";
}

string E_JsonStr(const string value)
{
   return "\"" + E_JsonEscape(value) + "\"";
}

string E_JsonNum(const double value)
{
   return E_FormatNumber(value);
}

// mid = (bid + ask) / 2  (contract requires this exact derivation)
double E_Mid(const double bid, const double ask)
{
   return (bid + ask) / 2.0;
}

// spread = ask - bid  (always >= 0 for a sane market)
double E_Spread(const double bid, const double ask)
{
   return ask - bid;
}

string E_Wrap(const string eventType, const string tsBridge, const string payloadBody)
{
   return "{\"event_type\":" + E_JsonStr(eventType)
          + ",\"source\":\"mql5\""
          + ",\"ts_bridge\":" + E_JsonStr(tsBridge)
          + ",\"payload\":{" + payloadBody + "}}";
}

//------------------------------------------------------------------+
// TICK_RECEIVED payload contract fields (contract section 4.1)     |
//   symbol, bid, ask, mid, spread, ts_source (+tick_volume)        |
// ts_source: real server time from the tick. Milliseconds are only |
// included when MQL5 provided them (tick.time_msc > 0); seconds are|
// never promoted to fake milliseconds.                             |
//------------------------------------------------------------------+
string E_BuildTickLine(const string symbol, const MqlTick &tick, const string tsBridge)
{
   string body = "\"symbol\":" + E_JsonStr(symbol)
                 + ",\"bid\":" + E_JsonNum(tick.bid)
                 + ",\"ask\":" + E_JsonNum(tick.ask)
                 + ",\"mid\":" + E_JsonNum(E_Mid(tick.bid, tick.ask))
                 + ",\"spread\":" + E_JsonNum(E_Spread(tick.bid, tick.ask))
                 + ",\"ts_source\":" + E_JsonStr(E_IsoTime(tick.time));
   double volumeReal = tick.volume_real;
   if(volumeReal <= 0.0)
      volumeReal = (double)tick.volume;
   if(volumeReal > 0.0)
      body += ",\"tick_volume\":" + IntegerToString((long)volumeReal);
   // tick_id is omitted on purpose: MQL5 provides no source-side unique
   // tick identifier and the bridge never fabricates one.
   return E_Wrap("TICK_RECEIVED", tsBridge, body);
}

//------------------------------------------------------------------+
// Execution telemetry (contract sections 4.8-4.11)                 |
// Broker ids are passed verbatim as strings (never generated).     |
//------------------------------------------------------------------+
string E_BuildOrderAckLine(const string symbol, const string brokerOrderId,
                           const string brokerState, const datetime ackTime,
                           const string tsBridge)
{
   string body = "\"broker_order_id\":" + E_JsonStr(brokerOrderId)
                 + ",\"broker_state\":" + E_JsonStr(brokerState)
                 + ",\"ack_ts\":" + E_JsonStr(E_IsoTime(ackTime));
   return E_Wrap("ORDER_ACKNOWLEDGED", tsBridge, body);
}

string E_BuildOrderFillLine(const string symbol, const string brokerOrderId,
                            const string brokerDealId, const double fillPrice,
                            const double fillVolume, const double slippage,
                            const datetime fillTime, const string tsBridge)
{
   string body = "\"broker_order_id\":" + E_JsonStr(brokerOrderId)
                 + ",\"broker_deal_id\":" + E_JsonStr(brokerDealId)
                 + ",\"fill_price\":" + E_JsonNum(fillPrice)
                 + ",\"fill_volume\":" + E_JsonNum(fillVolume)
                 + ",\"slippage\":" + E_JsonNum(slippage)
                 + ",\"fill_ts\":" + E_JsonStr(E_IsoTime(fillTime));
   return E_Wrap("ORDER_FILLED", tsBridge, body);
}

string E_BuildPositionOpenedLine(const string symbol, const string brokerPositionId,
                                 const string direction, const double volume,
                                 const double openPrice, const datetime openTime,
                                 const string tsBridge)
{
   string body = "\"broker_position_id\":" + E_JsonStr(brokerPositionId)
                 + ",\"direction\":" + E_JsonStr(direction)
                 + ",\"volume\":" + E_JsonNum(volume)
                 + ",\"open_price\":" + E_JsonNum(openPrice)
                 + ",\"open_ts\":" + E_JsonStr(E_IsoTime(openTime))
                 + ",\"state\":\"OPEN\"";
   return E_Wrap("POSITION_OPENED", tsBridge, body);
}

string E_BuildPositionUpdatedLine(const string symbol, const string brokerPositionId,
                                  const string direction, const double currentPrice,
                                  const double runningPnl, const double runningNetPnl,
                                  const double spreadCurrent, const string tsBridge)
{
   // mfe_usd / mae_usd: the bridge has no per-trade extremum tracking;
   // they are emitted as 0.0 raw evidence and the collector, which owns
   // trade-level state, is the authority for those values.
   string body = "\"broker_position_id\":" + E_JsonStr(brokerPositionId)
                 + ",\"current_price\":" + E_JsonNum(currentPrice)
                 + ",\"running_pnl_usd\":" + E_JsonNum(runningPnl)
                 + ",\"running_net_pnl_usd\":" + E_JsonNum(runningNetPnl)
                 + ",\"mfe_usd\":0.0"
                 + ",\"mae_usd\":0.0"
                 + ",\"spread_current\":" + E_JsonNum(spreadCurrent);
   return E_Wrap("POSITION_UPDATED", tsBridge, body);
}

string E_BuildPositionClosedLine(const string symbol, const string brokerPositionId,
                                 const double exitPrice, const double exitVolume,
                                 const datetime exitTime, const double realizedPnl,
                                 const double transactionCost, const double netPnl,
                                 const string exitReason, const string tsBridge)
{
   string body = "\"broker_position_id\":" + E_JsonStr(brokerPositionId)
                 + ",\"exit_fill_price\":" + E_JsonNum(exitPrice)
                 + ",\"exit_fill_volume\":" + E_JsonNum(exitVolume)
                 + ",\"exit_fill_ts\":" + E_JsonStr(E_IsoTime(exitTime))
                 + ",\"realized_pnl_usd\":" + E_JsonNum(realizedPnl)
                 + ",\"transaction_cost_usd\":" + E_JsonNum(transactionCost)
                 + ",\"net_pnl_usd\":" + E_JsonNum(netPnl)
                 + ",\"exit_reason\":" + E_JsonStr(exitReason)
                 + ",\"final_state\":\"CLOSED\"";
   return E_Wrap("POSITION_CLOSED", tsBridge, body);
}

//------------------------------------------------------------------+
// ERROR / TIMEOUT (contract sections 4.16-4.17)                    |
//------------------------------------------------------------------+
string E_BuildErrorLine(const string errorCode, const string severity,
                        const string message, const string tsBridge)
{
   string body = "\"error_code\":" + E_JsonStr(errorCode)
                 + ",\"component\":\"mql5-bridge\""
                 + ",\"severity\":" + E_JsonStr(severity)
                 + ",\"message\":" + E_JsonStr(message);
   return E_Wrap("ERROR", tsBridge, body);
}

string E_BuildTimeoutLine(const string timeoutCode, const string severity,
                          const string message, const string tsBridge)
{
   string body = "\"timeout_code\":" + E_JsonStr(timeoutCode)
                 + ",\"component\":\"mql5-bridge\""
                 + ",\"severity\":" + E_JsonStr(severity)
                 + ",\"message\":" + E_JsonStr(message);
   return E_Wrap("TIMEOUT", tsBridge, body);
}

//------------------------------------------------------------------+
// Bridge-internal evidence lines (non-canonical types)             |
//------------------------------------------------------------------+
// POSITION_SNAPSHOT: read-only evidence of open positions. The
// collector performs authoritative reconciliation (bridge never
// decides reconciliation outcomes).
string E_BuildPositionSnapshotLine(const string symbol,
                                   const string positionsBody,
                                   const string tsBridge)
{
   string body = "\"symbol\":" + E_JsonStr(symbol) + ",\"positions\":[" + positionsBody + "]";
   return E_Wrap("POSITION_SNAPSHOT", tsBridge, body);
}

string E_PositionSnapshotEntry(const string symbol, const string brokerPositionId,
                               const string direction, const double volume,
                               const double openPrice, const double currentPrice,
                               const string openTs, const string state)
{
   return "{\"broker_position_id\":" + E_JsonStr(brokerPositionId)
          + ",\"symbol\":" + E_JsonStr(symbol)
          + ",\"direction\":" + E_JsonStr(direction)
          + ",\"volume\":" + E_JsonNum(volume)
          + ",\"open_price\":" + E_JsonNum(openPrice)
          + ",\"current_price\":" + E_JsonNum(currentPrice)
          + ",\"open_ts\":" + E_JsonStr(openTs)
          + ",\"state\":" + E_JsonStr(state) + "}";
}

string E_BuildOrderSnapshotLine(const string symbol, const string ordersBody,
                                const string tsBridge)
{
   string body = "\"symbol\":" + E_JsonStr(symbol) + ",\"orders\":[" + ordersBody + "]";
   return E_Wrap("ORDER_SNAPSHOT", tsBridge, body);
}

string E_OrderSnapshotEntry(const string brokerOrderId, const string orderType,
                            const string orderState, const double priceOpen,
                            const double volume, const string setupTs)
{
   return "{\"broker_order_id\":" + E_JsonStr(brokerOrderId)
          + ",\"order_type\":" + E_JsonStr(orderType)
          + ",\"order_state\":" + E_JsonStr(orderState)
          + ",\"price_open\":" + E_JsonNum(priceOpen)
          + ",\"volume\":" + E_JsonNum(volume)
          + ",\"setup_ts\":" + E_JsonStr(setupTs) + "}";
}

string E_BuildHeartbeatLine(const string status, const bool terminalConnected,
                            const bool symbolAvailable, const string lastTickTs,
                            const bool exporterOk, const string lastWriteTs,
                            const int errorCount, const int tickCount,
                            const int writeCount, const int positionCount,
                            const int orderCount, const string tsBridge)
{
   string body = "\"status\":" + E_JsonStr(status)
                 + ",\"terminal_connected\":" + E_Bool(terminalConnected)
                 + ",\"symbol_available\":" + E_Bool(symbolAvailable)
                 + ",\"last_tick_ts\":" + E_JsonStr(lastTickTs)
                 + ",\"exporter_status\":" + E_JsonStr(exporterOk ? "ok" : "degraded")
                 + ",\"last_successful_write\":" + E_JsonStr(lastWriteTs)
                 + ",\"error_count\":" + IntegerToString(errorCount)
                 + ",\"tick_count\":" + IntegerToString(tickCount)
                 + ",\"write_count\":" + IntegerToString(writeCount)
                 + ",\"position_count\":" + IntegerToString(positionCount)
                 + ",\"order_count\":" + IntegerToString(orderCount);
   return E_Wrap("HEARTBEAT", tsBridge, body);
}