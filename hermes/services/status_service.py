def get_status() -> dict:
    from hermes.agents.types.monitor_agent import MonitorAgent
    agent = MonitorAgent.from_config()
    s = agent.get_status()
    return {
        "overall_healthy":  s.overall_healthy,
        "overall_severity": s.overall_severity,
        "watchers": [
            {
                "name":     w.name,
                "healthy":  w.healthy,
                "severity": w.severity,
                "message":  w.message,
            }
            for w in s.watchers
        ],
        "alerts": [
            {
                "name":     a.name,
                "severity": a.severity,
                "message":  a.message,
            }
            for a in s.alerts
        ],
    }
