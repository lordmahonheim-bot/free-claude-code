# Provider Rotation smoke tests

Smoke tests live reutilisables pour le Provider Rotation Engine de C-f-C.

## Objectif

- charger config/model_rings.yaml
- demarrer avec ENABLE_PROVIDER_ROTATION=true
- exposer /v1/provider-rotation/status
- router des requetes live /v1/messages
- persister la sante des providers dans SQLite
- verifier le fallback depuis un candidat invalide vers un candidat sain

## Commandes

Runtime simple:
cd /home/lord-mahonheim/projects/free-claude-code && uv run python smoke/provider_rotation_smoke.py runtime

Profils principaux:
cd /home/lord-mahonheim/projects/free-claude-code && uv run python smoke/provider_rotation_smoke.py profiles

Fallback controle:
cd /home/lord-mahonheim/projects/free-claude-code && uv run python smoke/provider_rotation_smoke.py fallback

Suite complete:
cd /home/lord-mahonheim/projects/free-claude-code && uv run python smoke/provider_rotation_smoke.py all

Wrapper equivalent:
cd /home/lord-mahonheim/projects/free-claude-code && ./smoke/provider_rotation_smoke.sh all

## Securite

- ne modifie pas config/model_rings.yaml
- cree les configs fallback temporaires sous /tmp/cfc_provider_rotation_fallback_*
- ecrit les artefacts sous workbench/output et memory_store
- ne doit pas afficher les cles API providers

## Ports utilises

Runtime: 18084
Profiles: 18085, 18086, 18087, 18088
Fallback: 18089, 18090

## Marqueurs attendus

SMOKE_PROVIDER_ROTATION_RUNTIME_OK=1
SMOKE_PROVIDER_ROTATION_PROFILES_OK=1
SMOKE_PROVIDER_ROTATION_FALLBACK_OK=1
SMOKE_PROVIDER_ROTATION_ALL_OK=1
