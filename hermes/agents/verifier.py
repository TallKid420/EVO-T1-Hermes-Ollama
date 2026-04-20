import requests
import subprocess
from dataclasses import dataclass
from typing import Optional

@dataclass
class VerificationResult:
    success: bool
    method: str          # "rule_based" or "llm_fallback"
    message: str
    next_action: Optional[str] = None
    requires_approval: bool = False


class VerifierAgent:
    def __init__(self, planner, notifier, allowlist: list):
        self.planner = planner
        self.notifier = notifier
        self.allowlist = allowlist

    def verify(self, task: dict, result: dict) -> VerificationResult:
        action = task.get("action")

        # --- Rule-based checks ---
        if action == "restart_service":
            return self._verify_service(task, result)
        
        if action == "cleanup_cache":
            return self._verify_cleanup(task, result)

        # --- Default: assume success if no rule exists ---
        return VerificationResult(success=True, method="rule_based", message="No rule defined, assumed success")

    def _verify_service(self, task: dict, result: dict) -> VerificationResult:
        service = task.get("action_args", {}).get("service")
        if not service:
            return VerificationResult(
                success=False,
                method="rule_based",
                message="Missing service in action_args",
                requires_approval=True,
            )

        # Rule 1: systemctl check
        status = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True
        ).stdout.strip()

        if status != "active":
            return self._llm_fallback(task, result, f"systemctl reports: {status}")

        # Rule 2: HTTP health check for ollama only
        if service == "ollama":
            try:
                r = requests.get("http://localhost:11434/api/tags", timeout=3)
                if r.status_code != 200:
                    return self._llm_fallback(task, result, f"Ollama HTTP check failed: {r.status_code}")
            except Exception as e:
                return self._llm_fallback(task, result, f"Ollama unreachable: {e}")

        return VerificationResult(success=True, method="rule_based", message=f"{service} is healthy")

    def _verify_cleanup(self, task: dict, result: dict) -> VerificationResult:
        # Rule: just check the command exited 0
        if result.get("exit_code") == 0:
            return VerificationResult(success=True, method="rule_based", message="Cleanup exited cleanly")
        return self._llm_fallback(task, result, f"Cleanup exit code: {result.get('exit_code')}")

    def _llm_fallback(self, task: dict, result: dict, failure_evidence: str) -> VerificationResult:
        # Ask the planner LLM what to do next
        event = {
            "message": f"Verification failed after action '{task['action']}'. Evidence: {failure_evidence}",
            "severity": "high"
        }
        llm_plan = self.planner.plan(event=event, system_status=result)
        suggested_action = llm_plan.get("action")

        # Validate against allowlist
        if suggested_action not in self.allowlist:
            return VerificationResult(
                success=False,
                method="llm_fallback",
                message=f"LLM suggested '{suggested_action}' which is outside allowlist",
                requires_approval=True
            )

        return VerificationResult(
            success=False,
            method="llm_fallback",
            message=f"LLM suggests: {suggested_action}",
            next_action=suggested_action,
            requires_approval=llm_plan.get("requires_approval", False)
        )