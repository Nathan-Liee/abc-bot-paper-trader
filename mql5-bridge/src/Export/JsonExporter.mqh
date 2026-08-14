//+------------------------------------------------------------------+
//| JsonExporter.mqh - append-only JSONL file exporter               |
//+------------------------------------------------------------------+
//| READ-ONLY TELEMETRY BRIDGE                                       |
//|                                                                    |
//| JSONL transport guarantees (see docs/ARCHITECTURE.md):            |
//|   - append-only: always opens FILE_READ|FILE_WRITE and seeks to   |
//|     the end; a corrupt/unreadable file is renamed (never          |
//|     overwritten) and a fresh file is started.                     |
//|   - one complete JSON object per line, terminated with LF.        |
//|   - ASCII-only output (non-ASCII escaped as \uXXXX) so the file   |
//|     is byte-for-byte UTF-8 compatible.                            |
//|   - atomic line write: a full line is written with a single       |
//|     FileWriteString call.                                         |
//|   - explicit flush policy: caller flushes via Flush() (Bridge     |
//|     flushes every InpFlushLines writes, every heartbeat, and in   |
//|     OnDeinit).                                                    |
//+------------------------------------------------------------------+
#property strict

#define BRIDGE_EXPORTER_CP_UTF8 65001

class CJsonExporter
{
private:
   int    m_handle;
   string m_path;
   int    m_errorCount;
   int    m_reopenAttempts;
   int    m_maxReopenAttempts;
   bool   m_corruptFileRenamed;

public:
   CJsonExporter()
      : m_handle(INVALID_HANDLE),
        m_path(""),
        m_errorCount(0),
        m_reopenAttempts(0),
        m_maxReopenAttempts(3),
        m_corruptFileRenamed(false)
   {
   }

   bool Open(const string path, const int maxReopenAttempts)
   {
      m_path = path;
      m_maxReopenAttempts = maxReopenAttempts;
      m_handle = OpenAppend(m_path);
      return m_handle != INVALID_HANDLE;
   }

   bool IsOpen() const
   {
      return m_handle != INVALID_HANDLE;
   }

   bool AppendLine(const string line)
   {
      if(!IsOpen())
      {
         if(!ReopenAfterFailure())
            return false;
      }
      uint written = FileWriteString(m_handle, line + "\n");
      int err = GetLastError();
      if(written == 0 || err != 0)
      {
         m_errorCount++;
         m_reopenAttempts = 0;
         return false;
      }
      m_reopenAttempts = 0;
      return true;
   }

   void Flush()
   {
      if(IsOpen())
         FileFlush(m_handle);
   }

   void Close()
   {
      if(IsOpen())
      {
         FileFlush(m_handle);
         FileClose(m_handle);
         m_handle = INVALID_HANDLE;
      }
   }

   int ErrorCount() const
   {
      return m_errorCount;
   }

   bool CorruptFileRenamed() const
   {
      return m_corruptFileRenamed;
   }

private:
   int OpenAppend(const string path)
   {
      int handle = FileOpen(path, FILE_READ | FILE_WRITE | FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_ANSI,
                            0, BRIDGE_EXPORTER_CP_UTF8);
      if(handle == INVALID_HANDLE)
         return INVALID_HANDLE;
      if(!FileSeek(handle, 0, SEEK_END))
      {
         FileClose(handle);
         return INVALID_HANDLE;
      }
      return handle;
   }

   // Bounded recovery: reopen; if the file itself is unreadable it is
   // renamed to "<name>.corrupted.<ts>" (historical stream preserved)
   // and a fresh file is started. Never blocks forever: bounded by
   // m_maxReopenAttempts.
   bool ReopenAfterFailure()
   {
      if(m_reopenAttempts >= m_maxReopenAttempts)
         return false;
      m_reopenAttempts++;

      int handle = OpenAppend(m_path);
      if(handle != INVALID_HANDLE)
      {
         m_handle = handle;
         return true;
      }

      if(!m_corruptFileRenamed)
      {
         string backup = m_path + ".corrupted." + string(TimeCurrent());
         if(FileMove(m_path, 0, backup, 0))
         {
            m_corruptFileRenamed = true;
            m_reopenAttempts = 0;
            handle = OpenAppend(m_path);
            if(handle != INVALID_HANDLE)
            {
               m_handle = handle;
               return true;
            }
         }
      }
      return false;
   }
};
