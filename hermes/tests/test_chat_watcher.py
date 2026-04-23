"""
Tests for ChatWatcher — buffer draining, Telegram filtering, no-message path.
No real network calls.
"""
import pytest
from unittest.mock import MagicMock, patch
from hermes.watchers.chat_watcher import ChatWatcher, _TelegramSource, _TerminalSource


TG_CFG = {
    "telegram": {
        "input": True,
        "token": "fake_token",
        "allowed_user_ids": [111],
        "poll_timeout": 1,
    }
}


# --- no sources enabled returns triggered=False ---

def test_check_no_messages_returns_not_triggered():
    with patch.object(_TerminalSource, "__init__", lambda self: None), \
         patch.object(_TerminalSource, "drain", return_value=[]):
        watcher = ChatWatcher(cfg={})
        watcher._buffer = []
        result = watcher.check()
    assert result.triggered is False


# --- buffered message is returned ---

def test_check_returns_buffered_message():
    with patch.object(_TerminalSource, "__init__", lambda self: None), \
         patch.object(_TerminalSource, "drain", return_value=[]):
        watcher = ChatWatcher(cfg={})
        watcher._buffer = [{
            "source": "terminal",
            "chat_id": "local",
            "user_id": "local",
            "text": "hello hermes",
            "message_id": None,
        }]
        result = watcher.check()
    assert result.triggered is True
    assert result.message == "hello hermes"
    assert result.source == "terminal"


# --- only one message returned per check, rest stay buffered ---

def test_check_pops_one_message_per_tick():
    with patch.object(_TerminalSource, "__init__", lambda self: None), \
         patch.object(_TerminalSource, "drain", return_value=[]):
        watcher = ChatWatcher(cfg={})
        watcher._buffer = [
            {"source": "terminal", "chat_id": "local", "user_id": "local", "text": "msg1", "message_id": None},
            {"source": "terminal", "chat_id": "local", "user_id": "local", "text": "msg2", "message_id": None},
        ]
        r1 = watcher.check()
        r2 = watcher.check()
    assert r1.message == "msg1"
    assert r2.message == "msg2"


# --- Telegram source filters unauthorized users ---

def test_telegram_source_filters_unauthorized():
    source = _TelegramSource(token="fake", allowed_user_ids=[111], timeout=1)
    fake_update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": 999},   # not in allowed list
            "chat": {"id": 999},
            "text": "hack attempt",
        }
    }
    with patch("requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {"result": [fake_update]}
        messages = source.drain()
    assert messages == []


# --- Telegram source passes authorized users ---

def test_telegram_source_passes_authorized():
    source = _TelegramSource(token="fake", allowed_user_ids=[111], timeout=1)
    fake_update = {
        "update_id": 2,
        "message": {
            "message_id": 2,
            "from": {"id": 111},
            "chat": {"id": 111},
            "text": "status check",
        }
    }
    with patch("requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {"result": [fake_update]}
        messages = source.drain()
    assert len(messages) == 1
    assert messages[0]["text"] == "status check"
    assert messages[0]["source"] == "telegram"


# --- Telegram source advances offset ---

def test_telegram_source_advances_offset():
    source = _TelegramSource(token="fake", allowed_user_ids=[], timeout=1)
    assert source._offset is None
    fake_update = {
        "update_id": 42,
        "message": {
            "message_id": 1,
            "from": {"id": 1},
            "chat": {"id": 1},
            "text": "hi",
        }
    }
    with patch("requests.get") as mock_get:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {"result": [fake_update]}
        source.drain()
    assert source._offset == 43


# --- Telegram network failure returns empty list, doesn't raise ---

def test_telegram_source_network_failure_returns_empty():
    source = _TelegramSource(token="fake", allowed_user_ids=[], timeout=1)
    with patch("requests.get", side_effect=ConnectionError("timeout")):
        messages = source.drain()
    assert messages == []