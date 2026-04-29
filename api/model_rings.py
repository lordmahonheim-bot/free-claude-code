"""Load provider rotation model rings from YAML configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from api.rotation_engine import ModelCandidate, ModelRing
from config.provider_catalog import SUPPORTED_PROVIDER_IDS


@dataclass(frozen=True, slots=True)
class RotationProfile:
    """Profile metadata for choosing a default model ring and weights."""

    name: str
    default_ring: str
    weights: dict[str, float]


@dataclass(frozen=True, slots=True)
class ModelRingsConfig:
    """Validated model rings configuration."""

    profiles: dict[str, RotationProfile]
    rings: dict[str, ModelRing]

    def get_profile(self, profile_name: str) -> RotationProfile:
        try:
            return self.profiles[profile_name]
        except KeyError as exc:
            raise ValueError(f"Unknown provider rotation profile: {profile_name}") from exc

    def get_ring(self, ring_name: str) -> ModelRing:
        try:
            return self.rings[ring_name]
        except KeyError as exc:
            raise ValueError(f"Unknown provider rotation ring: {ring_name}") from exc


def load_model_rings(path: str | Path) -> ModelRingsConfig:
    """Load and validate model rings from a YAML file."""
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("model rings config must be a mapping")

    profiles_raw = raw.get("profiles")
    rings_raw = raw.get("rings")
    if not isinstance(profiles_raw, dict):
        raise ValueError("model rings config must contain a profiles mapping")
    if not isinstance(rings_raw, dict):
        raise ValueError("model rings config must contain a rings mapping")

    rings = _parse_rings(rings_raw)
    profiles = _parse_profiles(profiles_raw, rings)

    return ModelRingsConfig(profiles=profiles, rings=rings)


def _parse_profiles(
    profiles_raw: dict[str, Any], rings: dict[str, ModelRing]
) -> dict[str, RotationProfile]:
    profiles: dict[str, RotationProfile] = {}
    for name, value in profiles_raw.items():
        if not isinstance(name, str) or not name:
            raise ValueError("profile name must be a non-empty string")
        if not isinstance(value, dict):
            raise ValueError(f"profile '{name}' must be a mapping")

        default_ring = value.get("default_ring")
        if not isinstance(default_ring, str) or not default_ring:
            raise ValueError(f"profile '{name}' must define default_ring")
        if default_ring not in rings:
            raise ValueError(
                f"profile '{name}' references unknown default ring '{default_ring}'"
            )

        weights_raw = value.get("weights", {})
        if not isinstance(weights_raw, dict):
            raise ValueError(f"profile '{name}' weights must be a mapping")
        weights = {
            str(weight_name): float(weight_value)
            for weight_name, weight_value in weights_raw.items()
        }

        profiles[name] = RotationProfile(
            name=name,
            default_ring=default_ring,
            weights=weights,
        )

    if not profiles:
        raise ValueError("model rings config must define at least one profile")
    return profiles


def _parse_rings(rings_raw: dict[str, Any]) -> dict[str, ModelRing]:
    rings: dict[str, ModelRing] = {}
    for name, candidates_raw in rings_raw.items():
        if not isinstance(name, str) or not name:
            raise ValueError("ring name must be a non-empty string")
        if not isinstance(candidates_raw, list):
            raise ValueError(f"ring '{name}' must be a list of candidates")

        candidates = tuple(_parse_candidate(name, item) for item in candidates_raw)
        rings[name] = ModelRing(name=name, candidates=candidates)

    if not rings:
        raise ValueError("model rings config must define at least one ring")
    return rings


def _parse_candidate(ring_name: str, raw: Any) -> ModelCandidate:
    if not isinstance(raw, dict):
        raise ValueError(f"ring '{ring_name}' candidate must be a mapping")

    model_ref = raw.get("model_ref")
    if not isinstance(model_ref, str) or "/" not in model_ref:
        raise ValueError(f"ring '{ring_name}' candidate model_ref must be provider/model")

    provider_id = model_ref.split("/", 1)[0]
    if provider_id not in SUPPORTED_PROVIDER_IDS:
        raise ValueError(
            f"ring '{ring_name}' candidate references unsupported provider '{provider_id}'"
        )

    priority = int(raw.get("priority", 100))
    weight = float(raw.get("weight", 1.0))
    capabilities_raw = raw.get("capabilities")
    if capabilities_raw is None:
        capabilities: tuple[str, ...] = ()
    elif isinstance(capabilities_raw, list):
        capabilities = tuple(str(item) for item in capabilities_raw)
    else:
        raise ValueError(f"ring '{ring_name}' candidate capabilities must be a list")

    return ModelCandidate(
        model_ref=model_ref,
        priority=priority,
        weight=weight,
        capabilities=capabilities,
    )
