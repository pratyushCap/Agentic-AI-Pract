from datetime import datetime, timezone
from typing import Any, Dict, List


def record_event(
    events: List[Dict[str, Any]],
    event_type: str,
    **details: Any,
) -> List[Dict[str, Any]]:
    """Append a serializable audit event and return the same event list."""
    events.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        **details,
    })
    return events
