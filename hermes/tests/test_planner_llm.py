# tests/test_planner_llm.py
from hermes.agents.planner.agent import Planner

def test_llm_plan():
    planner = Planner()

    event = {
        "type": "high_cpu",
        "severity": "warning",
        "message": "CPU usage at 91% for 5 minutes",
        "payload": {"cpu_percent": 91}
    }

    system_status = {
        "cpu_percent": 91,
        "ram_used_gb": 28,
        "disk_percent": 60
    }

    result = planner.plan(event=event, system_status=system_status)

    # Schema checks
    assert "action" in result, "Missing action"
    assert "action_args" in result, "Missing action_args"
    assert "requires_approval" in result, "Missing requires_approval"
    assert "reasoning" in result, "Missing reasoning"
    assert "risk_score" in result, "Missing risk_score"
    assert isinstance(result["requires_approval"], bool), "requires_approval must be bool"
    assert result.get("_fallback") != True, f"LLM failed: {result}"

    print("✅ LLM plan test passed")
    print(result)

if __name__ == "__main__":
    test_llm_plan()