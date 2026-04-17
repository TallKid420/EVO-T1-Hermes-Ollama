from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


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