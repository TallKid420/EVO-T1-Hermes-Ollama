import json
import logging
import yaml
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

        if agent_cfg.get("agent_type") == "builtin":
            response = _dispatch_builtin(agent_cfg.get("handler"), text)
        else:
            response = ChatProvider().send_chat_message(text, cfg=agent_cfg, stream=False)
    except Exception as exc:
        log.error("Agent '%s' failed: %s", agent_name, exc)
        _reply(source, chat_id, f"Agent error: {exc}", plugins_cfg)
        return

    _reply(source, chat_id, str(response), plugins_cfg)


def _dispatch_builtin(handler: str, text: str) -> str:
    """Run a builtin Python agent and return a human-readable string response."""
    if handler == "monitor_agent":
        from hermes.agents.monitor_agent import MonitorAgent
        agent = MonitorAgent.from_config()
        status = agent.get_status()
        lines = [status.summary_text]
        if status.alerts:
            for a in status.alerts:
                lines.append(f"  • {a.name}: {a.message} (severity={a.severity})")
        else:
            for w in status.watchers:
                lines.append(f"  • {w.name}: {w.message}")
        return "\n".join(lines)

    if handler == "filesystem_agent":
        from hermes.agents.filesystem_agent import FilesystemAgent
        with open("config/services.yaml", "r") as f:
            services_cfg = yaml.safe_load(f) or {}
        with open("config/filesystem.yaml", "r") as f:
            fs_cfg = yaml.safe_load(f) or {}
        agent = FilesystemAgent(services_cfg, fs_cfg)

        text_lower = text.lower()
        if any(w in text_lower for w in ("clean", "delete", "free", "purge", "clear")):
            plan = agent.scan()
            if not plan.targets:
                return "No reclaimable paths found."
            results = agent.execute_plan(plan)
            freed = sum(r.bytes_freed for r in results)
            lines = [f"Cleanup complete. ~{freed / 1e6:.1f} MB freed."]
            for r in results:
                lines.append(f"  • {r.path}: {r.status}")
            return "\n".join(lines)
        else:
            summary = agent.status_summary()
            total_mb = summary["total_reclaimable_bytes"] / 1e6
            lines = [
                f"Filesystem scan: {summary['scannable_targets']} target(s), "
                f"~{total_mb:.1f} MB reclaimable."
            ]
            for t in summary["targets"]:
                lines.append(
                    f"  • {t['path']}: {t['size_bytes'] / 1e6:.1f} MB "
                    f"({t['file_count']} files)"
                )
            if summary["skipped_paths"]:
                lines.append(f"  Skipped (not safe): {summary['skipped_paths']}")
            return "\n".join(lines)

    raise ValueError(f"Unknown builtin handler: {handler!r}")


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
