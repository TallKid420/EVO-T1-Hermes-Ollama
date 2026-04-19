# tests/test_verifier_rules.py
from unittest.mock import patch, MagicMock
from hermes.agents.verifier import VerifierAgent

def test_verify_service_healthy():
    mock_planner = MagicMock()
    mock_notifier = MagicMock()
    allowlist = ["restart_service", "cleanup_cache", "send_notification"]

    verifier = VerifierAgent(planner=mock_planner, notifier=mock_notifier, allowlist=allowlist)

    task = {
        "action": "restart_service",
        "action_args": {"service": "ollama"}
    }
    exec_result = {"exit_code": 0}

    # Mock systemctl → active
    # Mock ollama HTTP → 200
    with patch("subprocess.run") as mock_sub, \
         patch("requests.get") as mock_get:

        mock_sub.return_value = MagicMock(stdout="active")
        mock_get.return_value = MagicMock(status_code=200)

        result = verifier.verify(task=task, exec_result=exec_result)

    assert result.success == True, f"Expected success, got: {result.message}"
    assert result.method == "rule_based"
    assert mock_planner.plan.called == False, "LLM should NOT have been called"

    print("✅ Verifier rule-based (healthy) test passed")
    print(result)


def test_verify_service_unhealthy():
    mock_planner = MagicMock()
    mock_notifier = MagicMock()
    allowlist = ["restart_service", "cleanup_cache", "send_notification"]

    # LLM fallback returns a valid plan
    mock_planner.plan.return_value = {
        "action": "send_notification",
        "action_args": {"message": "Ollama still down after restart"},
        "requires_approval": False,
        "reasoning": "Service still unhealthy",
        "risk_score": 3
    }

    verifier = VerifierAgent(planner=mock_planner, notifier=mock_notifier, allowlist=allowlist)

    task = {
        "action": "restart_service",
        "action_args": {"service": "ollama"}
    }
    exec_result = {"exit_code": 0}

    # Mock systemctl → inactive
    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(stdout="inactive")

        result = verifier.verify(task=task, exec_result=exec_result)

    assert result.success == False
    assert result.method == "llm_fallback"
    assert mock_planner.plan.called == True, "LLM SHOULD have been called"

    print("✅ Verifier LLM fallback test passed")
    print(result)


if __name__ == "__main__":
    test_verify_service_healthy()
    test_verify_service_unhealthy()