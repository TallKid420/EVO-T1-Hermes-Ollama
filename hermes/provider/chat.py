import json
import requests
import yaml
from typing import Dict, Any

class ChatProvider:
    def __init__(self):
        pass
        
    def send_message(self, prompt: str, cfg: Dict[str, Any], format: str | None = None, stream: bool = False) -> tuple[str, list[dict], bool]:
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
                timeout_seconds=int(cfg.get("timeout_seconds")), 
                stream=stream,
                _format=format
            )
        raise ValueError(f"Unsupported provider: {provider}")

class OllamaChatProvider(ChatProvider):
    def __init__(self):
        super().__init__()

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
        
