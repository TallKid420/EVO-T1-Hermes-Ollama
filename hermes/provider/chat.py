import json
import requests
import yaml
from typing import Dict, Any

class ChatProvider:
    def __init__(self):
        pass
        
    def send_message(self, prompt: str, cfg: Dict[str, Any], format: str | None = None, stream: bool = False) -> tuple[str, list[dict], bool]:
        provider = cfg.get("provider")
        if provider == "ollama":
            return OllamaChatProvider().ollama_chat(
                prompt=prompt, 
                endpoint=cfg.get("endpoint"), 
                model=cfg.get("model"), 
                timeout_seconds=int(cfg.get("timeout_seconds")), 
                stream=stream,
                _format=format
            )

class OllamaChatProvider(ChatProvider):
    def __init__(self):
        super().__init__()

    def ollama_chat(self, prompt: str, endpoint: str, model: str, timeout_seconds: int, stream: bool, _format = None) -> tuple[str, list[dict], bool]:
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
        
