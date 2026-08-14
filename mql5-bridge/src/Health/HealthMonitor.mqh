//+------------------------------------------------------------------+
//| HealthMonitor.mqh - bridge health counters and state             |
//+------------------------------------------------------------------+
//| READ-ONLY TELEMETRY BRIDGE                                       |
//| Pure bookkeeping: counts ticks/writes/errors, remembers the last |
//| tick and the last successful write. Never touches execution.    |
//+------------------------------------------------------------------+
#property strict

class CHealthMonitor
{
private:
   int      m_tickCount;
   int      m_writeCount;
   int      m_errorCount;
   datetime m_lastTickTime;
   datetime m_lastWriteOkTime;
   bool     m_terminalConnected;
   bool     m_symbolAvailable;

public:
   void Reset()
   {
      m_tickCount = 0;
      m_writeCount = 0;
      m_errorCount = 0;
      m_lastTickTime = 0;
      m_lastWriteOkTime = 0;
      m_terminalConnected = false;
      m_symbolAvailable = false;
   }

   void OnTickSeen(const MqlTick &tick)
   {
      m_tickCount++;
      m_lastTickTime = tick.time;
   }

   void OnWrite(const bool ok)
   {
      if(ok)
      {
         m_writeCount++;
         m_lastWriteOkTime = TimeTradeServer();
      }
      else
      {
         m_errorCount++;
      }
   }

   void OnError()
   {
      m_errorCount++;
   }

   void SetTerminalConnected(const bool connected)
   {
      m_terminalConnected = connected;
   }

   void SetSymbolAvailable(const bool available)
   {
      m_symbolAvailable = available;
   }

   int TickCount() const
   {
      return m_tickCount;
   }

   int WriteCount() const
   {
      return m_writeCount;
   }

   int ErrorCount() const
   {
      return m_errorCount;
   }

   datetime LastTickTime() const
   {
      return m_lastTickTime;
   }

   datetime LastWriteOkTime() const
   {
      return m_lastWriteOkTime;
   }

   bool TerminalConnected() const
   {
      return m_terminalConnected;
   }

   bool SymbolAvailable() const
   {
      return m_symbolAvailable;
   }
};