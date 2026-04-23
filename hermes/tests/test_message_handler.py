"""
Tests for message_handler — router dispatch, builtin agents, reply routing.
All external calls (LLM, Telegram, file I/O) are mocked.
"""
import pytest
from unittest.mock import MagicMock, patch
from hermes.watchers.base import WatcherResult
from hermes.core.severity import Severity
from hermes.chat.message_handler import handle_user_message, _reply, _dispatch_builtin


PLUGINS_CFG = {
    "active": {"communication": {"telegram": {"input": True, "output": True}}},
    "plugins": {"telegram": {"token": "fake", "chat_id": "123"}},
}

AGENTS_CFG = {
    "custom_agents": {
        "paperclip": {
            "agent_type": "llm",
            "provider": "ollama",
            "model": "llama3",
            "endpoint": "http://localhost:11434",
            "timeout_seconds": 30,
        },
        "monitor_agent": {
            "agent_type": "builtin",
            "handler": "monitor_agent",
            "description": "System health",
        },
        "filesystem_agent": {
            "agent_type": "builtin",
            "handler": "filesystem_agent",
            "description": "Filesystem cleanup",
        },
    }
}


def _make_result(source: str, text: str) -> WatcherResult:
    return WatcherResult(
        triggered=True,
        severity=Severity.INFO,
        event_type="user_message",
        source=source,
        message=text,
        payload={"source": source, "chat_id": "123", "text": text, "message_id": 1},
    )


# --- terminal reply ---

def test_reply_terminal(capsys):
    _reply("terminal", "local", "Hello from Hermes", PLUGINS_CFG)
    captured = capsys.readouterr()
    assert "Hello from Hermes" in captured.out


# --- telegram reply ---

def test_reply_telegram():
    with patch("hermes.chat.message_handler.TelegramCommunicationPlugin") as MockBot:
        instance = MockBot.return_value
        _reply("telegram", "456", "Hi there", PLUGINS_CFG)
        MockBot.assert_called_once()
        instance.send.assert_called_once_with("Hi there")


# --- unknown source logs warning, doesn't raise ---

def test_reply_unknown_source_no_raise():
    _reply("discord", "123", "test", PLUGINS_CFG)   # should not raise


# --- router failure sends error reply ---

def test_handle_user_message_router_failure(capsys):
    result = _make_result("terminal", "hello")
    with patch("hermes.chat.message_handler.ChatListener") as MockListener:
        MockListener.return_value.router.side_effect = RuntimeError("LLM down")
        handle_user_message(result, PLUGINS_CFG, AGENTS_CFG)
    captured = capsys.readouterr()
    assert "Router error" in captured.out


# --- router returns no agent ---

def test_handle_user_message_no_agent(capsys):
    result = _make_result("terminal", "hello")
    with patch("hermes.chat.message_handler.ChatListener") as MockListener:
        MockListener.return_value.router.return_value = {"agent": None}
        handle_user_message(result, PLUGINS_CFG, AGENTS_CFG)
    captured = capsys.readouterr()
    assert "could not determine" in captured.out


# --- LLM agent dispatch ---

def test_handle_user_message_llm_agent(capsys):
    result = _make_result("terminal", "help me")
    with patch("hermes.chat.message_handler.ChatListener") as MockListener, \
         patch("hermes.chat.message_handler.ChatProvider") as MockProvider:
        MockListener.return_value.router.return_value = {"agent": "paperclip"}
        MockProvider.return_value.send_chat_message.return_value = "Sure, here you go."
        handle_user_message(result, PLUGINS_CFG, AGENTS_CFG)
    captured = capsys.readouterr()
    assert "Sure, here you go." in captured.out


# --- builtin monitor_agent dispatch ---

def test_dispatch_builtin_monitor_agent():
    mock_status = MagicMock()
    mock_status.summary_text = "All systems nominal."
    mock_status.alerts = []
    mock_status.watchers = []

    with patch("hermes.agents.monitor_agent.MonitorAgent.from_config") as MockAgent:
        MockAgent.return_value.get_status.return_value = mock_status
        response = _dispatch_builtin("monitor_agent", "status")
    assert "All systems nominal." in response


# --- builtin filesystem_agent scan dispatch ---

def test_dispatch_builtin_filesystem_scan():
    mock_summary = {
        "scannable_targets": 1,
        "total_reclaimable_bytes": 5_000_000,
        "targets": [{"path": "/tmp/cache", "size_bytes": 5_000_000, "file_count": 10}],
        "skipped_paths": [],
    }
    with patch("hermes.agents.filesystem_agent.FilesystemAgent") as MockAgent, \
         patch("builtins.open", MagicMock()), \
         patch("yaml.safe_load", return_value={}):
        MockAgent.return_value.status_summary.return_value = mock_summary
        response = _dispatch_builtin("filesystem_agent", "how much space can I free?")
    assert "5.0 MB" in response


# --- unknown builtin handler raises ---

def test_dispatch_builtin_unknown_raises():
    with pytest.raises(ValueError, match="Unknown builtin handler"):
        _dispatch_builtin("nonexistent_handler", "test")