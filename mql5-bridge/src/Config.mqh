//+------------------------------------------------------------------+
//| Config.mqh - single configuration point for the MQL5 bridge      |
//+------------------------------------------------------------------+
//| READ-ONLY TELEMETRY BRIDGE                                       |
//| This bridge NEVER places, modifies, or deletes orders.           |
//| It only reads market/terminal state and writes JSONL telemetry.  |
//+------------------------------------------------------------------+
#property strict

// Symbol is configured ONCE here. It is never hard-coded elsewhere in
// the bridge; every component receives it as a parameter.
input string InpSymbol = "XAUUSDc";                    // Symbol to monitor
input string InpEventFile = "data\\raw\\mql5_bridge_events.jsonl";  // Output path (relative to MQL5\Files)
input int InpHeartbeatSec = 5;                        // Heartbeat emission interval (seconds)
input int InpSnapshotSec = 30;                        // Position/order snapshot interval (seconds)
input int InpPositionUpdateSec = 5;                   // POSITION_UPDATED telemetry interval (seconds)
input int InpFlushLines = 100;                        // Flush file after this many writes
input int InpMaxReopenAttempts = 3;                   // Bounded reopen retries after write failure
