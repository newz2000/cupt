"""
Tests for cupt/ai.py — focuses on graceful degradation when local AI
providers are unavailable (no SDK, model not supported, runtime errors).
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _try_apple_intelligence
# ---------------------------------------------------------------------------


def test_try_apple_intelligence_no_sdk():
    """Returns None gracefully when apple_fm_sdk is not installed."""
    with patch.dict(sys.modules, {"apple_fm_sdk": None}):
        from cupt.ai import _try_apple_intelligence

        result = _try_apple_intelligence("write a note")
        assert result is None


def test_try_apple_intelligence_not_available():
    """Returns None when SDK is present but the model reports unavailable."""
    mock_fm = MagicMock()
    mock_fm.SystemLanguageModel.return_value.is_available.return_value = (
        False,
        "requires macOS 26",
    )
    with patch.dict(sys.modules, {"apple_fm_sdk": mock_fm}):
        from cupt.ai import _try_apple_intelligence

        result = _try_apple_intelligence("write a note")
        assert result is None


def test_try_apple_intelligence_success():
    """Returns the model's text when AI is available."""
    mock_fm = MagicMock()
    mock_fm.SystemLanguageModel.return_value.is_available.return_value = (True, "ok")

    with patch.dict(sys.modules, {"apple_fm_sdk": mock_fm}):
        with patch("asyncio.run", return_value="Completed the analysis."):
            from cupt.ai import _try_apple_intelligence

            result = _try_apple_intelligence("write a note")
            assert result == "Completed the analysis."


def test_try_apple_intelligence_strips_whitespace():
    """Strips leading/trailing whitespace from the model response."""
    mock_fm = MagicMock()
    mock_fm.SystemLanguageModel.return_value.is_available.return_value = (True, "ok")

    with patch.dict(sys.modules, {"apple_fm_sdk": mock_fm}):
        with patch("asyncio.run", return_value="  Completed.  \n"):
            from cupt.ai import _try_apple_intelligence

            result = _try_apple_intelligence("write a note")
            assert result == "Completed."


def test_try_apple_intelligence_runtime_exception():
    """Returns None when the model raises an unexpected exception."""
    mock_fm = MagicMock()
    mock_fm.SystemLanguageModel.return_value.is_available.return_value = (True, "ok")

    with patch.dict(sys.modules, {"apple_fm_sdk": mock_fm}):
        with patch("asyncio.run", side_effect=RuntimeError("model crashed")):
            from cupt.ai import _try_apple_intelligence

            result = _try_apple_intelligence("write a note")
            assert result is None


# ---------------------------------------------------------------------------
# get_ai_suggestion (public interface)
# ---------------------------------------------------------------------------


def test_get_ai_suggestion_no_providers():
    """Returns None when all providers are unavailable."""
    with patch("cupt.ai._try_apple_intelligence", return_value=None):
        from cupt.ai import get_ai_suggestion

        result = get_ai_suggestion("write a note")
        assert result is None


def test_get_ai_suggestion_returns_first_provider():
    """Returns the result from the first successful provider."""
    with patch("cupt.ai._try_apple_intelligence", return_value="Great work done."):
        from cupt.ai import get_ai_suggestion

        result = get_ai_suggestion("write a note")
        assert result == "Great work done."


# ---------------------------------------------------------------------------
# is_ai_available
# ---------------------------------------------------------------------------


def test_is_ai_available_no_sdk():
    """Returns False when apple_fm_sdk is not installed."""
    with patch.dict(sys.modules, {"apple_fm_sdk": None}):
        from cupt.ai import is_ai_available

        assert is_ai_available() is False


def test_is_ai_available_not_supported():
    """Returns False when SDK is present but model is unavailable."""
    mock_fm = MagicMock()
    mock_fm.SystemLanguageModel.return_value.is_available.return_value = (
        False,
        "not supported",
    )
    with patch.dict(sys.modules, {"apple_fm_sdk": mock_fm}):
        from cupt.ai import is_ai_available

        assert is_ai_available() is False


def test_is_ai_available_supported():
    """Returns True when the model is available."""
    mock_fm = MagicMock()
    mock_fm.SystemLanguageModel.return_value.is_available.return_value = (True, "ok")
    with patch.dict(sys.modules, {"apple_fm_sdk": mock_fm}):
        from cupt.ai import is_ai_available

        assert is_ai_available() is True
