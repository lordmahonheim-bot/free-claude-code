# Système de Mémoire pour free-claude-code

Stockage persistant et exploitable des conversations utilisateur/assistant.

## Structure

```
memory/
├── __init__.py          # Exports principaux
├── memory_manager.py    # Orchestrateur central
├── storage_sqlite.py    # Backend SQLite
├── exporter_md.py       # Export Markdown lisible
├── retriever.py         # Recherche et récupération de contexte
├── integration.py       # Intégration avec le proxy
├── config.py            # Configuration
└── cli.py               # Interface en ligne de commande

memory_store/
├── memory.db            # Base SQLite
└── sessions/            # Fichiers Markdown exportés
    └── session_xxxx.md
```

## Utilisation CLI

```bash
# Recherche dans la mémoire
python memory/cli.py search "docker"

# Liste des sessions récentes
python memory/cli.py sessions --limit 10

# Statistiques
python memory/cli.py stats

# Export d'une session
python memory/cli.py export <session_id>
```

## Intégration dans le Proxy

Dans `api/routes.py`, remplacer `get_proxy_service`:

```python
from memory.integration import create_memory_enabled_service

def get_proxy_service(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Build the memory-enabled request service."""
    return create_memory_enabled_service(
        settings=settings,
        provider_getter=lambda provider_type: dependencies.resolve_provider(
            provider_type, app=request.app, settings=settings
        ),
        token_counter=get_token_count,
    )
```

## Variables d'Environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `MEMORY_ENABLED` | Activer la mémoire | `true` |
| `MEMORY_DB_PATH` | Chemin base SQLite | `memory_store/memory.db` |
| `MEMORY_EXPORT_DIR` | Dossier sessions Markdown | `memory_store/sessions` |
| `MEMORY_MARKDOWN` | Activer export Markdown | `true` |
| `MEMORY_CONTEXT_MESSAGES` | Messages récents à injecter | `4` |
| `MEMORY_MAX_SEARCH_RESULTS` | Résultats de recherche max | `5` |

## Schéma Base de Données

### Table `sessions`
- `session_id` (TEXT PRIMARY KEY)
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)
- `summary` (TEXT)

### Table `messages`
- `message_id` (INTEGER PRIMARY KEY)
- `session_id` (TEXT, FK)
- `timestamp` (TIMESTAMP)
- `role` (TEXT: 'user', 'assistant')
- `content` (TEXT)
- `model` (TEXT)
- `provider` (TEXT)
- `metadata` (TEXT: JSON)

### Table `summaries`
- `summary_id` (INTEGER PRIMARY KEY)
- `session_id` (TEXT, FK, UNIQUE)
- `summary` (TEXT)
- `created_at` (TIMESTAMP)
