import json


def format_event(name: str, data: dict) -> bytes:
    """Encode one SSE event; JSON has no raw newline, so one data line suffices."""
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {name}\ndata: {payload}\n\n".encode()
