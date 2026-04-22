import logging
from typing import Any, Dict

from hermes.chat.chat_listener import ChatListener
from hermes.plugins.communication.telegram import TelegramCommunicationPlugin
from hermes.plugins.provider.chat import ChatProvider
from hermes.watchers.base import WatcherResult


log = logging.getLogger(__name__)


def handle_user_message(result: WatcherResult, plugins_cfg: Dict[str, Any], agents_cfg: Dict[str, Any]) -> None:
    """Route a chat message to an agent and send the response back to the source."""
    payload = result.payload or {}
    source = payload.get("source")
    chat_id = payload.get("chat_id")
    text = payload.get("text", "")

    log.info("user_message from %s: %r", source, text)

    try:
        listener = ChatListener(plugincfg=plugins_cfg, agentcfg=agents_cfg)
        route = listener.router(text)
        agent_name = route.get("agent") if isinstance(route, dict) else None
    except Exception as exc:
        log.error("Router failed: %s", exc)
        _reply(source, chat_id, "Router error: could not determine agent.", plugins_cfg)
        return

    if not agent_name:
        log.warning("Router returned no agent for message: %r", text)
        _reply(source, chat_id, "I could not determine how to handle that message.", plugins_cfg)
        return

    log.info("Routing to agent: %s", agent_name)

    try:
        agent_cfg = dict(agents_cfg.get("custom_agents", {}).get(agent_name, {}))
        if not agent_cfg:
            raise ValueError(f"No config found for agent '{agent_name}'")
        agent_cfg["agent_name"] = agent_name
        response = ChatProvider().send_chat_message(text, cfg=agent_cfg, stream=False)
    except Exception as exc:
        log.error("Agent '%s' failed: %s", agent_name, exc)
        _reply(source, chat_id, f"Agent error: {exc}", plugins_cfg)
        return

    _reply(source, chat_id, str(response), plugins_cfg)


def _reply(source: str, chat_id: Any, text: str, plugins_cfg: Dict[str, Any]) -> None:
    """Send a reply to the source channel."""
    if source == "terminal":
        print(f"\n[Hermes] {text}\n")
        return

    if source == "telegram":
        try:
            tg_cfg = dict(plugins_cfg.get("plugins", {}).get("telegram", {}))
            if chat_id is not None:
                tg_cfg["chat_id"] = str(chat_id)
            bot = TelegramCommunicationPlugin(tg_cfg)
            bot.send(text)
        except Exception as exc:
            log.error("Telegram reply failed: %s", exc)
        return

    log.warning("Unknown source '%s' - cannot reply", source)
