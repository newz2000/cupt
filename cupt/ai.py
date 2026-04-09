"""
Local AI backend abstraction for CUPT.

Provider priority:
  1. Apple Intelligence (apple-fm-sdk, macOS 26+)

Future providers (not yet implemented):
  2. Windows Copilot+ (WinRT Microsoft.Windows.AI)
  3. Ollama (http://localhost:11434)
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTIONS = (
    "You are a concise assistant helping a professional complete task management notes. "
    "Write clear, brief, first-person completion notes. No preamble or explanation."
)


def get_ai_suggestion(prompt: str) -> Optional[str]:
    """
    Try available local AI backends and return a suggestion, or None if unavailable.

    Returns None silently when no provider is found — callers are responsible
    for surfacing a user-facing message.
    """
    result = _try_apple_intelligence(prompt)
    if result is not None:
        return result

    # Future: _try_windows_copilot(prompt)
    # Future: _try_ollama(prompt)

    return None


def is_ai_available() -> bool:
    """Return True if at least one local AI provider is available."""
    return _apple_intelligence_available()


# ------------------------------------------------------------------
# Apple Intelligence
# ------------------------------------------------------------------


def _apple_intelligence_available() -> bool:
    try:
        import apple_fm_sdk as fm

        available, _ = fm.SystemLanguageModel().is_available()
        return available
    except ImportError:
        return False
    except Exception:
        return False


def _try_apple_intelligence(prompt: str) -> Optional[str]:
    try:
        import apple_fm_sdk as fm

        model = fm.SystemLanguageModel()
        available, reason = model.is_available()
        if not available:
            logger.debug("Apple Intelligence not available: %s", reason)
            return None

        session = fm.LanguageModelSession(instructions=_SYSTEM_INSTRUCTIONS)
        result = asyncio.run(session.respond(prompt))
        return result.strip() if result else None

    except ImportError:
        logger.debug("apple-fm-sdk not installed")
        return None
    except Exception as e:
        logger.debug("Apple Intelligence error: %s", e)
        return None
