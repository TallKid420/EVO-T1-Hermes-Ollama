import json
import requests
from typing import Dict, Any

class ChatProvider:
    def __init__(self):
        pass

    def send_system_message(self, prompt: str, cfg: Dict[str, Any], format: str | None = None, stream: bool = False) -> tuple[str, list[dict], bool]:
        provider = cfg.get("provider")
        if not provider:
            raise ValueError("Missing required chat provider config: provider")
        if not cfg.get("endpoint"):
            raise ValueError("Missing required chat provider config: endpoint")
        if not cfg.get("model"):
            raise ValueError("Missing required chat provider config: model")
        if cfg.get("timeout_seconds") is None:
            raise ValueError("Missing required chat provider config: timeout_seconds")
        if provider == "ollama":
            return OllamaChatProvider().ollama_generate(
                prompt=prompt, 
                endpoint=cfg.get("endpoint"), 
                model=cfg.get("model"),
                timeout_seconds=cfg.get("timeout_seconds"),
                stream=stream,
                _format=format
            )
        raise ValueError(f"Unsupported provider: {provider}")
        
    def send_chat_message(self, prompt: str, cfg: Dict[str, Any], format: str | None = None, stream: bool = False) -> tuple[str, list[dict], bool]:
        provider = cfg.get("provider")
        if not provider:
            raise ValueError("Missing required chat provider config: provider")
        if not cfg.get("endpoint"):
            raise ValueError("Missing required chat provider config: endpoint")
        if not cfg.get("model"):
            raise ValueError("Missing required chat provider config: model")
        if cfg.get("timeout_seconds") is None:
            raise ValueError("Missing required chat provider config: timeout_seconds")
        if provider == "ollama":
            return OllamaChatProvider().ollama_chat(
                prompt=prompt, 
                cfg=cfg,
                stream=stream,
                _format=format
            )
        raise ValueError(f"Unsupported provider: {provider}")

class OllamaChatProvider(ChatProvider):
    _verified_custom_models: Dict[str, tuple[str, str]] = {}

    def __init__(self):
        super().__init__()

    def _list_models(self, endpoint: str, timeout_seconds: int) -> list[str]:
        resp = requests.get(f"{endpoint}/api/tags", timeout=timeout_seconds)
        resp.raise_for_status()
        return [m.get("name") for m in resp.json().get("models", []) if m.get("name")]

    def _show_model(self, endpoint: str, model: str, timeout_seconds: int) -> Dict[str, Any]:
        resp = requests.post(
            f"{endpoint}/api/show",
            json={"model": model, "verbose": True},
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def _delete_model(self, endpoint: str, model: str, timeout_seconds: int) -> None:
        resp = requests.delete(
            f"{endpoint}/api/delete",
            json={"model": model},
            timeout=timeout_seconds,
        )
        # Older servers may only accept POST /api/delete.
        if resp.status_code in (404, 405):
            resp = requests.post(
                f"{endpoint}/api/delete",
                json={"model": model},
                timeout=timeout_seconds,
            )
        resp.raise_for_status()

    def _create_model(self, endpoint: str, model: str, base_model: str, system_prompt: str, timeout_seconds: int) -> None:
        payload: Dict[str, Any] = {
            "model": model,
            "from": base_model,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        resp = requests.post(
            f"{endpoint}/api/create",
            json=payload,
            timeout=max(timeout_seconds, 300),
        )
        resp.raise_for_status()

    def _ensure_custom_model(self, cfg: Dict[str, Any]) -> str:
        endpoint = str(cfg.get("endpoint") or "").strip()
        configured_model = str(cfg.get("model") or "").strip()
        model = str(cfg.get("agent_name") + ":latest").strip()
        timeout_seconds = int(cfg.get("timeout_seconds") or 30)
        expected_system = str(cfg.get("system_prompt") or cfg.get("system") or "").strip()
        expected_base = configured_model

        # Reconciliation is only for custom models carrying explicit base/system constraints.
        if not model or (not expected_base and not expected_system):
            print("No custom model configuration detected; using configured model directly.")
            return configured_model or model

        cache_key = f"{endpoint}|{model}"
        cached = self._verified_custom_models.get(cache_key)
        if cached == (expected_base, expected_system):
            print(f"Using cached verification for model '{model}' on endpoint '{endpoint}'.")
            return model

        available = self._list_models(endpoint, timeout_seconds)

        if model not in available:
            if not expected_base:
                raise ValueError(
                    f"Custom model '{model}' does not exist and no base model is configured. "
                    "Set from_model/base_model/from in config."
                )
            if expected_base not in available:
                raise ValueError(
                    f"Base model '{expected_base}' is missing on Ollama endpoint {endpoint}."
                )
            print(f"Model: {model}")
            print(f"Available: {available}")
            self._create_model(endpoint, model, expected_base, expected_system, timeout_seconds)
            self._verified_custom_models[cache_key] = (expected_base, expected_system)
            return model

        if not expected_base:
            # Can't validate parent_model without an expected base; treat as verified by existence+system rule.
            model_data = self._show_model(endpoint, model, timeout_seconds)
            actual_system = str(model_data.get("system") or "").strip()
            if expected_system and actual_system != expected_system:
                raise ValueError(
                    f"Model '{model}' system prompt differs from config, but no base model is set for safe recreation. "
                    "Set from_model/base_model/from in config."
                )
            self._verified_custom_models[cache_key] = (expected_base, expected_system)
            return model

        model_data = self._show_model(endpoint, model, timeout_seconds)
        actual_system = str(model_data.get("system") or "").strip()
        details = model_data.get("details") or {}
        actual_parent = str(details.get("parent_model") or "").strip()

        base_mismatch = (actual_parent != expected_base)
        system_mismatch = bool(expected_system) and (actual_system != expected_system)
        if base_mismatch or system_mismatch:
            self._delete_model(endpoint, model, timeout_seconds)
            self._create_model(endpoint, model, expected_base, expected_system, timeout_seconds)

        self._verified_custom_models[cache_key] = (expected_base, expected_system)
        return model

    def ollama_chat(self, prompt: str, cfg: Dict[str, Any], stream: bool, _format: str = None) -> tuple[str, list[dict], bool]:
        endpoint = cfg.get("endpoint")
        timeout_seconds = int(cfg.get("timeout_seconds"))
        model = self._ensure_custom_model(cfg)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }
        if _format is not None:
            payload["format"] = _format

        response = requests.post(
            f"{endpoint}/api/chat",
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()

        data = response.json()
        content = data.get("message", {}).get("content", "")
        if _format == "json":
            return json.loads(content)
        return content

    def ollama_generate(self, prompt: str, endpoint: str, model: str, timeout_seconds: int, stream: bool, _format: str = None) -> tuple[str, list[dict], bool]:
        if _format is None:
            response = requests.post(
                f"{endpoint}/api/generate",
                json={"model": model, "prompt": prompt, "stream": stream},
                timeout=timeout_seconds
            )
            return response.json().get("response")
        else:
            response = requests.post(
                f"{endpoint}/api/generate",
                json={"model": model, "prompt": prompt, "stream": stream, "format": _format},
                timeout=timeout_seconds
            )
            return json.loads(response.json()["response"])