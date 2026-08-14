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
//|   - parent directories are created before every open (idempotent, |
//|     relative to MQL5\Files); creation failure is explicit.        |
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
      string normalized = NormalizePath(path);
      if(normalized == "")
      {
         Print("mql5-bridge: empty event file path; exporter disabled");
         return false;
      }
      m_path = normalized;
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
   // Normalize path to MQL5\Files-relative form: accept both slash
   // styles, strip leading separators, never allow an absolute path.
   string NormalizePath(const string path)
   {
      string s = path;
      StringReplace(s, "/", "\\");
      while(StringLen(s) > 0 && StringGetCharacter(s, 0) == '\\')
         s = StringSubstr(s, 1);
      return s;
   }

   // Directory part of a relative file path ("" when none).
   string DirectoryOf(const string path)
   {
      string segments[];
      int count = StringSplit(path, '\\', segments);
      if(count <= 1)
         return "";
      string dir = segments[0];
      for(int i = 1; i < count - 1; i++)
         dir += "\\" + segments[i];
      return dir;
   }

   // Idempotent directory creation relative to MQL5\Files, segment by
   // segment (build-safe: does not rely on recursive FolderCreate).
   //   - existing directory  -> no-op success
   //   - missing directory   -> created
   //   - creation failure    -> explicit error with the MQL5 error code
   bool EnsureDirectory(const string dirPath)
   {
      if(dirPath == "")
         return true;
      string segments[];
      int count = StringSplit(dirPath, '\\', segments);
      string acc = "";
      for(int i = 0; i < count; i++)
      {
         if(StringLen(segments[i]) == 0)
            continue;
         if(StringLen(acc) > 0)
            acc += "\\";
         acc += segments[i];
         if(FolderCreate(acc))
            continue;
         // Some builds return false for an already-existing folder;
         // only a real error (GetLastError() != 0) is a failure.
         if(GetLastError() != 0)
         {
            Print("mql5-bridge: cannot create directory '", acc, "' "
                  "(error ", IntegerToString(GetLastError()), ")");
            return false;
         }
      }
      return true;
   }

   int OpenAppend(const string path)
   {
      if(!EnsureDirectory(DirectoryOf(path)))
         return INVALID_HANDLE;
      int handle = FileOpen(path, FILE_READ | FILE_WRITE | FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_ANSI,
                            0, BRIDGE_EXPORTER_CP_UTF8);
      if(handle == INVALID_HANDLE)
      {
         Print("mql5-bridge: cannot open '", path, "' (error ",
               IntegerToString(GetLastError()), ")");
         return INVALID_HANDLE;
      }
      if(!FileSeek(handle, 0, SEEK_END))
      {
         Print("mql5-bridge: cannot seek to end of '", path, "' (error ",
               IntegerToString(GetLastError()), ")");
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
