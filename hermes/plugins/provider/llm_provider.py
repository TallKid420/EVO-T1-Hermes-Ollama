from hermes.config_loader import AgentConfig


def LLMProvider(config: AgentConfig):
    match config.provider:
        case "ollama":
            return Ollama(config)
        case _:
            raise ValueError(f"Unsupported provider: {config.provider}")


def Ollama(config: AgentConfig):
    from langchain_ollama import ChatOllama

    try:
        llm = ChatOllama(
            model=config.model,
            base_url=config.endpoint,
            temperature=config.temperature,
        )
    except Exception as e:
        raise ValueError(f"Failed to initialize Ollama: {e}")

    return llm
