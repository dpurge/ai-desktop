from backend.sse import format_event


def test_format_event_has_name_json_data_and_blank_line_terminator():
    assert (
        format_event("text_delta", {"text": "hi"}) == b'event: text_delta\ndata: {"text":"hi"}\n\n'
    )


def test_format_event_keeps_newlines_inside_json_string():
    encoded = format_event("text_delta", {"text": "a\nb"})
    assert encoded == b'event: text_delta\ndata: {"text":"a\\nb"}\n\n'
