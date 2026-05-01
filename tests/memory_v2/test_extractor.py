from types import SimpleNamespace

from memory_v2.extractor import extract_last_user_text, extract_text_from_content


def test_extract_text_from_plain_string():
    assert extract_text_from_content("Bonjour") == "Bonjour"


def test_extract_text_from_anthropic_blocks():
    content = [
        {"type": "text", "text": "Analyse"},
        {"type": "image", "source": {"type": "base64"}},
        {"type": "text", "text": "ce document"},
    ]

    assert extract_text_from_content(content) == "Analyse\nce document"


def test_extract_last_user_text_from_dict_payload():
    payload = {
        "messages": [
            {"role": "user", "content": "Ancienne question"},
            {"role": "assistant", "content": "Ancienne réponse"},
            {"role": "user", "content": [{"type": "text", "text": "Dernière question"}]},
        ]
    }

    assert extract_last_user_text(payload) == "Dernière question"


def test_extract_last_user_text_from_object_payload():
    payload = SimpleNamespace(
        messages=[
            SimpleNamespace(role="assistant", content="Réponse"),
            SimpleNamespace(role="user", content="Question objet"),
        ]
    )

    assert extract_last_user_text(payload) == "Question objet"


def test_extract_last_user_text_returns_empty_without_user_message():
    payload = {"messages": [{"role": "assistant", "content": "Seulement assistant"}]}

    assert extract_last_user_text(payload) == ""
