from hermes.db import store


def list_events(limit: int = 50, unacked_only: bool = False) -> list:
    events = store.list_events(limit=limit, unacked_only=unacked_only)
    return [_serialize_event(e) for e in events]


def add_event(severity: str, source: str, type_: str, message: str, payload: dict = None) -> dict:
    event_id = store.add_event(
        severity=severity,
        source=source,
        type_=type_,
        message=message,
        payload=payload or {},
    )
    return {"status": "created", "event_id": event_id}


def _serialize_event(e) -> dict:
    return {
        "id":         e.id,
        "created_at": e.created_at,
        "severity":   e.severity,
        "type":       e.type,
        "source":     e.source,
        "message":    e.message,
    }