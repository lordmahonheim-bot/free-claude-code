# Intégration Mémoire - Guide rapide

## Option 1: Intégration automatique (recommandé)

```bash
# Activer la mémoire
python -m memory.patch_routes

# Si besoin de restaurer
python -m memory.patch_routes --restore
```

## Option 2: Intégration manuelle

Modifier `api/routes.py` :

```python
# En haut du fichier, ajouter:
from memory.hooks import before_request, after_response

# Modifier create_message
@router.post("/v1/messages")
async def create_message(
    request_data: MessagesRequest,
    service: ClaudeProxyService = Depends(get_proxy_service),
    settings: Settings = Depends(get_settings),
    _auth=Depends(require_api_key),
):
    """Create a message (always streaming) with memory."""
    session_id = before_request(request_data, n_context=4)
    model = getattr(request_data, "model", None) or settings.model
    provider = settings.provider_type

    response = service.create_message(request_data)

    return after_response(session_id, response, request_data, model, provider)
```

## Test

```bash
# Test unitaire du stockage
python memory/simple_test.py

# Test CLI
python memory/cli.py stats

# Recherche
python memory/cli.py search "docker"
```

## Vérifier que ça marche

1. Envoyer une requête au proxy via Claude Code
2. Vérifier le stockage :
   ```bash
   sqlite3 memory_store/memory.db "SELECT COUNT(*) FROM messages;"
   ```
3. Vérifier les exports Markdown :
   ```bash
   ls memory_store/sessions/
   ```

## Structure résultante

```
memory_store/
├── memory.db              # Base SQLite
└── sessions/
    └── session_xxxx.md    # Conversations exportées
```

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `MEMORY_ENABLED` | `true` | Activer/désactiver |
| `MEMORY_DB_PATH` | `memory_store/memory.db` | Chemin base |
| `MEMORY_CONTEXT_MESSAGES` | `4` | Messages historiques à injecter |
| `MEMORY_MARKDOWN` | `true` | Exporter en Markdown |
