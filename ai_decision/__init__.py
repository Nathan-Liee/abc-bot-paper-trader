"""AI Decision Engine for ABC Bot.

Pure proposal layer: consumes market context, produces a BUY/SELL/NO-TRADE
proposal with confidence and reason. It NEVER computes risk, lot, SL, exposure,
margin, execution, or exit — those remain system authority. See
docs/validation/ai-decision-engine/ai-decision-engine-validation.md and
docs/contracts/canonical-event-contract.md (AI_REQUEST / AI_RESPONSE events).
"""

from __future__ import annotations

from ai_decision.config import EngineConfig, ModelConfig, load_config
from ai_decision.engine import DecisionEngine
from ai_decision.prompt import PROMPT_VERSION
from ai_decision.record import DecisionRecord

__all__ = [
    "DecisionEngine",
    "DecisionRecord",
    "EngineConfig",
    "ModelConfig",
    "PROMPT_VERSION",
    "load_config",
]

__version__ = "0.1.0"
