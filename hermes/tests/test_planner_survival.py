# tests/test_planner_survival.py
from hermes.agents.planner.agent import Planner

def test_survival_override():
    planner = Planner()

    event = {
        "type": "service_unhealthy",
        "severity": "critical",
        "message": "Ollama is down",
        "payload": {"service": "ollama"}
    }

    result = planner.plan(event=event, system_status={})

    assert result["action"] == "restart_service", f"Expected restart_service, got {result['action']}"
    assert result["action_args"]["service"] == "ollama", "Missing service name"
    assert result.get("_override") == True, "Should be marked as survival override"
    assert result["requires_approval"] == False

    print("✅ Survival override test passed")
    print(result)

if __name__ == "__main__":
    test_survival_override()