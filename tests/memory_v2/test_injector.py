from memory_v2.injector import (
    MEMORY_HEADER,
    build_memory_context,
    inject_system_context,
)


def test_build_memory_context_from_turns():
    context = build_memory_context(
        [
            {
                "user_text": "Question ancienne",
                "assistant_text": "Réponse ancienne",
                "provider": "nvidia_nim",
                "model": "model-a",
                "status": "completed",
            }
        ]
    )

    assert MEMORY_HEADER in context
    assert "Question ancienne" in context
    assert "Réponse ancienne" in context
    assert "nvidia_nim/model-a" in context


def test_inject_system_context_when_system_missing():
    payload = {"messages": []}
    injected = inject_system_context(payload, "MEMORY")

    assert injected["system"] == "MEMORY"
    assert "system" not in payload


def test_inject_system_context_prepends_string_system():
    payload = {"system": "Instruction existante", "messages": []}
    injected = inject_system_context(payload, "MEMORY")

    assert injected["system"].startswith("MEMORY")
    assert "Instruction existante" in injected["system"]
    assert injected["system"].index("MEMORY") < injected["system"].index("Instruction existante")


def test_inject_system_context_prepends_list_system():
    payload = {
        "system": [{"type": "text", "text": "Instruction existante"}],
        "messages": [],
    }
    injected = inject_system_context(payload, "MEMORY")

    assert injected["system"][0] == {"type": "text", "text": "MEMORY"}
    assert injected["system"][1]["text"] == "Instruction existante"


def test_empty_context_does_not_modify_payload_semantics():
    payload = {"system": "Instruction", "messages": []}
    injected = inject_system_context(payload, "")

    assert injected == payload
    assert injected is not payload
