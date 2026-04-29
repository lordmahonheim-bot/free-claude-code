from pathlib import Path

import pytest

from api.model_rings import load_model_rings


def test_load_default_model_rings_config():
    config = load_model_rings("config/model_rings.yaml")

    assert "stable-agentic" in config.profiles
    assert "code_agentic" in config.rings
    assert config.get_profile("stable-agentic").default_ring == "code_agentic"
    assert config.get_ring("code_agentic").candidates[0].provider_id == "nvidia_nim"


def test_load_model_rings_rejects_unknown_provider(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
profiles:
  stable:
    default_ring: code
rings:
  code:
    - model_ref: unknown_provider/model
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported provider"):
        load_model_rings(path)


def test_load_model_rings_rejects_profile_with_unknown_default_ring(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
profiles:
  stable:
    default_ring: missing
rings:
  code:
    - model_ref: nvidia_nim/model
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown default ring"):
        load_model_rings(path)


def test_load_model_rings_rejects_missing_rings_mapping(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
profiles:
  stable:
    default_ring: code
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="rings mapping"):
        load_model_rings(path)


def test_get_unknown_profile_and_ring_raise_clear_errors():
    config = load_model_rings("config/model_rings.yaml")

    with pytest.raises(ValueError, match="Unknown provider rotation profile"):
        config.get_profile("missing")

    with pytest.raises(ValueError, match="Unknown provider rotation ring"):
        config.get_ring("missing")
