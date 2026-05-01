from memory_v2.stream_capture import SSEStreamCapture


def test_stream_capture_collects_text_delta():
    lines = [
        'event: message_start',
        'data: {"type":"message_start","message":{"model":"test-model"}}',
        'event: content_block_delta',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Bon"}}',
        'event: content_block_delta',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"jour"}}',
        'event: message_delta',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
    ]

    result = SSEStreamCapture().feed_lines(lines)

    assert result.text == "Bonjour"
    assert result.model == "test-model"
    assert result.stop_reason == "end_turn"
    assert result.errors == []


def test_stream_capture_accepts_bytes():
    lines = [
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"OK"}}',
    ]

    result = SSEStreamCapture().feed_lines(lines)

    assert result.text == "OK"


def test_stream_capture_records_json_errors():
    lines = [
        "data: {bad json",
    ]

    result = SSEStreamCapture().feed_lines(lines)

    assert result.text == ""
    assert len(result.errors) == 1
    assert result.errors[0].startswith("json_decode_error")


def test_stream_capture_records_error_event():
    lines = [
        'data: {"type":"error","error":{"type":"provider_error","message":"failed"}}',
    ]

    result = SSEStreamCapture().feed_lines(lines)

    assert result.text == ""
    assert len(result.errors) == 1
    assert "provider_error" in result.errors[0]


def test_stream_capture_accepts_multiline_sse_chunk():
    chunk = (
        'event: message_start\n'
        'data: {"type":"message_start","message":{"model":"runtime-model"}}\n'
        '\n'
        'event: content_block_delta\n'
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"OK_RUNTIME"}}\n'
        '\n'
        'event: message_delta\n'
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}\n'
    )

    result = SSEStreamCapture().feed_lines([chunk])

    assert result.text == "OK_RUNTIME"
    assert result.model == "runtime-model"
    assert result.stop_reason == "end_turn"
    assert result.errors == []
