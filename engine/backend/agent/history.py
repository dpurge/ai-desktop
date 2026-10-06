CANCELLED_TOOL_RESULT = "The turn was cancelled before this ran."


def repair_tool_results(messages: list[dict]) -> list[dict]:
    """Make every tool call answered exactly once, directly after its assistant message.

    The engine can be killed while a tool runs (the app quits), which leaves a stored log that
    every provider rejects. The log stays as written; only the copy sent to the model is fixed.
    Tool messages that answer no call announced just before them are dropped.
    """
    repaired: list[dict] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        index += 1
        if message["role"] == "tool":
            continue
        repaired.append(message)
        calls = message.get("tool_calls") if message["role"] == "assistant" else None
        if not calls:
            continue
        replies: dict[str, dict] = {}
        while index < len(messages) and messages[index]["role"] == "tool":
            replies.setdefault(messages[index]["tool_call_id"], messages[index])
            index += 1
        for call in calls:
            repaired.append(replies.get(call["id"]) or _cancelled_reply(call["id"]))
    return repaired


def _cancelled_reply(call_id: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": CANCELLED_TOOL_RESULT}
