from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class Event:
    id: int
    created_at: str
    severity: str
    source: str
    type: str
    message: str
    payload: Dict[str, Any]
    acknowledged_at: Optional[str]


@dataclass(frozen=True)
class Task:
    id: int
    created_at: str
    updated_at: str
    status: str
    priority: int
    type: str
    title: str
    payload: Dict[str, Any]
    result: Optional[Dict[str, Any]]
    event_id: Optional[int]
    requires_approval: bool
    approved_at: Optional[str]
    blocked_reason: Optional[str]
    attempts: int
    parent_agent: Optional[str] = None
    spawn_depth: int = 0


@dataclass(frozen=True)
class Action:
    id: int
    created_at: str
    task_id: Optional[int]
    tool: str
    action: str
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]]
    success: bool
    duration_ms: Optional[int]
    error: Optional[str]


@dataclass(frozen=True)
class AgentNode:
    id: int
    created_at: str
    updated_at: str
    agent_id: str
    parent_id: Optional[str]
    name: str
    type: str
    depth: int
    mailbox_id: str
    status: str
    meta: Dict[str, Any]


@dataclass(frozen=True)
class MailboxMessage:
    id: int
    created_at: str
    mailbox_id: str
    sender_agent_id: str
    message_type: str
    payload: Dict[str, Any]
    task_id: Optional[int]
    parent_message_id: Optional[int]
    status: str
    requires_ack: bool
    acknowledged_at: Optional[str]