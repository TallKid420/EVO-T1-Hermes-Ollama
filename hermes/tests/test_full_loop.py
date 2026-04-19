# tests/test_full_loop.py
from unittest.mock import patch, MagicMock
from hermes.agents.planner.agent import Planner
from hermes.agents.verifier import VerifierAgent

def test_full_loop():
    planner = Planner()
    mock_notifier = MagicMock()
    allowlist = ["restart_service", "cleanup_cache", "send_notification", "delete_files", "notify_user"]

    verifier = VerifierAgent(planner=planner, notifier=mock_notifier, allowlist=allowlist)

    # Step 1: Planner gets a survival event
    event = {
        "type": "service_unhealthy",
        "severity": "critical",
        "message": "Ollama is down",
        "payload": {"service": "ollama"}
    }

    plan = planner.plan(event=event, system_status={"cpu_percent": 40})
    print(f"Plan: {plan}")
    assert plan["action"] == "restart_service"

    # Step 2: Simulate executor ran and returned success
    exec_result = {"exit_code": 0}

    # Step 3: Verifier checks — mock systemctl + ollama HTTP as healthy
    with patch("subprocess.run") as mock_sub, \
         patch("requests.get") as mock_get:

        mock_sub.return_value = MagicMock(stdout="active")
        mock_get.return_value = MagicMock(status_code=200)

        verification = verifier.verify(task=plan, exec_result=exec_result)

    print(f"Verification: {verification}")
    assert verification.success == True
    assert verification.method == "rule_based"

    print("✅ Full loop test passed")

if __name__ == "__main__":
    test_full_loop()