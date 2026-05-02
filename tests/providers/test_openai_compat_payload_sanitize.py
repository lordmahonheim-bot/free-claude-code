from providers.openai_compat import _sanitize_provider_payload


def test_sanitize_provider_payload_removes_nested_none_values():
    body = {
        "model": "gemini-2.5-flash",
        "max_tokens": None,
        "temperature": None,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello", "cache_control": None}
                ],
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": None,
                    "parameters": {
                        "type": "object",
                        "required": None,
                        "properties": {
                            "query": {
                                "type": "string",
                                "minLength": None,
                                "maxLength": None,
                            }
                        },
                    },
                },
            }
        ],
    }

    clean = _sanitize_provider_payload(body)

    assert "max_tokens" not in clean
    assert "temperature" not in clean
    assert "cache_control" not in clean["messages"][0]["content"][0]
    assert "description" not in clean["tools"][0]["function"]
    assert "required" not in clean["tools"][0]["function"]["parameters"]
    query_schema = clean["tools"][0]["function"]["parameters"]["properties"]["query"]
    assert "minLength" not in query_schema
    assert "maxLength" not in query_schema
    assert query_schema["type"] == "string"
