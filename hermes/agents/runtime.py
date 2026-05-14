"""
hermes/agents/runtime.py

Agent runtime loop.
Each agent runs as an independent async worker:
  - polls its mailbox for incoming messages
  - claims tasks from the shared queue (filtered by type/ownership)
  - executes tasks via its tool registry
  - emits events and results back to the DB
  - enforces spawn depth and child limits
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional, Callable, Awaitable

from hermes.db.models import Task, MailboxMessage
from hermes.db.store import (
    register_agent_node,
    get_pending_mailbox_messages,
    send_mailbox_message,
    claim_next_queued_task,
    create_task,
    update_task_status,
    set_task_result,
    add_event,
    add_action,
)

log = logging.getLogger(__name__)

# Type alias for a task handler coroutine
TaskHandler = Callable[[Task], Awaitable[dict]]


class AgentRuntime:
    """
    Base runtime for all Hermes agents.
    Subclass this and implement `handle_task` and optionally `handle_message`.
    """

    # Override in subclass
    AGENT_TYPE: str = "base"
    HANDLED_TASK_TYPES: list[str] = []  # empty = claim nothing
    MAX_CHILDREN: int = 5
    MAX_SPAWN_DEPTH: int = 3
    POLL_INTERVAL: float = 1.0  # seconds between loop ticks
    MAILBOX_BATCH: int = 10

    def __init__(
        self,
        name: str,
        agent_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        spawn_depth: int = 0,
        config: Optional[dict] = None,
    ):
        self.name = name
        self.agent_id = agent_id or f"{self.AGENT_TYPE}_{uuid.uuid4().hex[:8]}"
        self.mailbox_id = self.agent_id
        self.parent_id = parent_id
        self.spawn_depth = spawn_depth
        self.config = config or {}
        self._running = False
        self._child_count = 0
        self._current_task: Optional[Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Register this agent and enter the main loop."""
        self._running = True
        self._register()
        log.info(f"[{self.name}] started (id={self.agent_id}, depth={self.spawn_depth})")
        try:
            await self._loop()
        except asyncio.CancelledError:
            log.info(f"[{self.name}] cancelled")
        except Exception as e:
            log.exception(f"[{self.name}] crashed: {e}")
            add_event(
                severity="error",
                source=self.agent_id,
                type_="agent_crash",
                message=str(e),
                payload={"agent_id": self.agent_id, "name": self.name},
            )
        finally:
            self._running = False
            self._set_node_status("offline")
            log.info(f"[{self.name}] stopped")

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _loop(self):
        while self._running:
            tick_start = time.monotonic()

            try:
                await self._process_mailbox()
            except Exception as e:
                log.warning(f"[{self.name}] mailbox error: {e}")

            try:
                await self._process_next_task()
            except Exception as e:
                log.warning(f"[{self.name}] task error: {e}")

            elapsed = time.monotonic() - tick_start
            sleep_for = max(0.0, self.POLL_INTERVAL - elapsed)
            await asyncio.sleep(sleep_for)

    # ------------------------------------------------------------------
    # Mailbox
    # ------------------------------------------------------------------

    async def _process_mailbox(self):
        messages = get_pending_mailbox_messages(self.mailbox_id, limit=self.MAILBOX_BATCH)
        for raw in messages:
            msg = MailboxMessage(**raw)
            try:
                await self.handle_message(msg)
                self._ack_message(msg.id)
            except Exception as e:
                log.warning(f"[{self.name}] failed to handle message {msg.id}: {e}")

    async def handle_message(self, msg: MailboxMessage):
        """
        Override to handle incoming mailbox messages.
        Default: convert task_request messages into queued tasks.
        """
        if msg.message_type == "task_request":
            payload = msg.payload
            self._create_child_task(
                type_=payload.get("type", "generic"),
                title=payload.get("title", "Delegated task"),
                payload=payload.get("data", {}),
                requires_approval=payload.get("requires_approval", False),
            )
        elif msg.message_type == "stop":
            log.info(f"[{self.name}] received stop signal via mailbox")
            self.stop()
        else:
            log.debug(f"[{self.name}] unhandled message type: {msg.message_type}")

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    async def _process_next_task(self):
        if not self.HANDLED_TASK_TYPES:
            return  # this agent doesn't claim tasks directly

        task = claim_next_queued_task()
        if task is None:
            return

        # Only handle task types this agent is responsible for
        if task.type not in self.HANDLED_TASK_TYPES:
            # Put it back by re-queuing (another agent will pick it up)
            update_task_status(task.id, "queued")
            return

        self._current_task = task
        log.info(f"[{self.name}] executing task {task.id}: {task.title}")

        t_start = time.monotonic()
        try:
            result = await self.handle_task(task)
            duration_ms = int((time.monotonic() - t_start) * 1000)

            set_task_result(task.id, result)
            update_task_status(task.id, "done")

            add_action(
                task_id=task.id,
                tool=self.AGENT_TYPE,
                action="execute_task",
                input_={"title": task.title, "type": task.type},
                output=result,
                success=True,
                duration_ms=duration_ms,
            )
            log.info(f"[{self.name}] task {task.id} done in {duration_ms}ms")

        except Exception as e:
            duration_ms = int((time.monotonic() - t_start) * 1000)
            update_task_status(task.id, "failed", blocked_reason=str(e))
            add_action(
                task_id=task.id,
                tool=self.AGENT_TYPE,
                action="execute_task",
                input_={"title": task.title, "type": task.type},
                output=None,
                success=False,
                duration_ms=duration_ms,
                error=str(e),
            )
            add_event(
                severity="error",
                source=self.agent_id,
                type_="task_failed",
                message=str(e),
                payload={"task_id": task.id, "title": task.title},
            )
            log.error(f"[{self.name}] task {task.id} failed: {e}")
        finally:
            self._current_task = None

    async def handle_task(self, task: Task) -> dict:
        """
        Override in subclass to implement task execution.
        Must return a result dict.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement handle_task()")

    # ------------------------------------------------------------------
    # Sub-agent spawning
    # ------------------------------------------------------------------

    def spawn_child(
        self,
        agent_class: type[AgentRuntime],
        name: str,
        config: Optional[dict] = None,
    ) -> Optional[AgentRuntime]:
        """
        Spawn a child agent with guardrails enforced.
        Returns the agent instance (caller must schedule it with asyncio).
        """
        if self.spawn_depth >= self.MAX_SPAWN_DEPTH:
            log.warning(
                f"[{self.name}] spawn blocked: max depth {self.MAX_SPAWN_DEPTH} reached"
            )
            add_event(
                severity="warning",
                source=self.agent_id,
                type_="spawn_blocked",
                message=f"Max spawn depth {self.MAX_SPAWN_DEPTH} reached",
                payload={"parent": self.agent_id, "attempted": name},
            )
            return None

        if self._child_count >= self.MAX_CHILDREN:
            log.warning(
                f"[{self.name}] spawn blocked: max children {self.MAX_CHILDREN} reached"
            )
            add_event(
                severity="warning",
                source=self.agent_id,
                type_="spawn_blocked",
                message=f"Max children {self.MAX_CHILDREN} reached",
                payload={"parent": self.agent_id, "attempted": name},
            )
            return None

        child = agent_class(
            name=name,
            parent_id=self.agent_id,
            spawn_depth=self.spawn_depth + 1,
            config=config or {},
        )
        self._child_count += 1
        log.info(
            f"[{self.name}] spawned child [{name}] "
            f"(depth={child.spawn_depth}, children={self._child_count})"
        )
        add_event(
            severity="info",
            source=self.agent_id,
            type_="agent_spawned",
            message=f"Spawned child agent: {name}",
            payload={
                "parent_id": self.agent_id,
                "child_id": child.agent_id,
                "depth": child.spawn_depth,
            },
        )
        return child

    def _create_child_task(
        self,
        type_: str,
        title: str,
        payload: dict,
        requires_approval: bool = False,
        priority: int = 5,
    ) -> int:
        """Create a task attributed to this agent."""
        return create_task(
            status="queued",
            priority=priority,
            type_=type_,
            title=title,
            payload=payload,
            requires_approval=requires_approval,
            parent_agent=self.agent_id,
            spawn_depth=self.spawn_depth,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _register(self):
        register_agent_node(
            agent_id=self.agent_id,
            parent_id=self.parent_id,
            name=self.name,
            type_=self.AGENT_TYPE,
            depth=self.spawn_depth,
            mailbox_id=self.mailbox_id,
            status="online",
            meta=self.config,
        )

    def _set_node_status(self, status: str):
        register_agent_node(
            agent_id=self.agent_id,
            parent_id=self.parent_id,
            name=self.name,
            type_=self.AGENT_TYPE,
            depth=self.spawn_depth,
            mailbox_id=self.mailbox_id,
            status=status,
            meta=self.config,
        )

    def _ack_message(self, message_id: int):
        """Mark a mailbox message as processed."""
        from hermes.db.conn import connect
        conn = connect()
        try:
            conn.execute(
                """
                UPDATE mailbox_messages
                SET status = 'processed', acknowledged_at = ?
                WHERE id = ?
                """,
                (_now_str(), message_id),
            )
            conn.commit()
        finally:
            conn.close()


def _now_str() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat()