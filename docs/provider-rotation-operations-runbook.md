# Provider Rotation — Runbook d'exploitation

Projet : Claude-free-code (C-f-C)
Chemin : `/home/lord-mahonheim/projects/free-claude-code`
Profil validé : `stable-agentic`
Config : `config/model_rings.yaml`
Health DB validée : `memory_store/provider_rotation_claude_code_real.db`

## 1. Objectif

Le Provider Rotation Engine permet à C-f-C de router les appels Claude Code vers un ring de modèles/providers, avec persistance de santé, suivi des succès/échecs et fallback.

Flux validé :

```text
Claude Code CLI -> proxy C-f-C :8082 -> Provider Rotation -> Cloudflare KIMI K2.6 -> retour Claude Code
```

## 2. Lancement du proxy

```bash
cd /home/lord-mahonheim/projects/free-claude-code && \
env \
  ENABLE_PROVIDER_ROTATION=true \
  PROVIDER_ROTATION_PROFILE=stable-agentic \
  PROVIDER_ROTATION_CONFIG=config/model_rings.yaml \
  PROVIDER_ROTATION_HEALTH_DB=memory_store/provider_rotation_claude_code_real.db \
  ANTHROPIC_AUTH_TOKEN=freecc \
  uv run uvicorn server:app --host 0.0.0.0 --port 8082
```

Critère de réussite : `Uvicorn running on http://0.0.0.0:8082`.

## 3. Vérification runtime

```bash
cd /home/lord-mahonheim/projects/free-claude-code && \
curl -s -H "Authorization: Bearer freecc" http://localhost:8082/v1/provider-rotation/status | uv run python -m json.tool
```

Critères attendus :

- `enabled: true`
- `profile: stable-agentic`
- `rings_loaded: true`
- `total_failure_count: 0` en fonctionnement nominal

## 4. Lancement Claude Code via proxy

```bash
cd /home/lord-mahonheim/projects/free-claude-code && \
unset CLAUDE_CODE_OAUTH_TOKEN && \
unset ANTHROPIC_AUTH_TOKEN && \
export ANTHROPIC_BASE_URL="http://localhost:8082" && \
export ANTHROPIC_API_KEY="freecc" && \
claude
```

Si Claude Code propose une ancienne clé Anthropic officielle, choisir `No`.

## 5. Test conversationnel

Prompt Claude Code :

```text
Réponds exactement avec ce marqueur: OK_PROVIDER_ROTATION_REAL
```

Le terminal proxy doit afficher des requêtes `POST /v1/messages?beta=true` en HTTP 200.

## 6. Test tool-use non destructif

Commande Bash autorisée dans Claude Code :

```bash
pwd && git branch --show-current && git status --short && test -f config/model_rings.yaml && echo MODEL_RINGS_PRESENT
```

Critères attendus : chemin projet correct, branche `main`, `MODEL_RINGS_PRESENT`, et `git status --short` vide.

## 7. Diagnostic rapide

- `/login` ou `invalid token` : Claude Code ne passe probablement pas par le proxy ou une session Anthropic interfère.
- `enabled: false` : relancer le proxy avec `ENABLE_PROVIDER_ROTATION=true`.
- `rings_loaded: false` : vérifier `PROVIDER_ROTATION_CONFIG=config/model_rings.yaml`.
- Absence de logs `/v1/messages?beta=true` : Claude Code ne cible pas `ANTHROPIC_BASE_URL=http://localhost:8082`.

## 8. Arrêt propre

Arrêter Uvicorn avec `Ctrl+C`, puis vérifier :

```bash
ss -ltnp | grep ":8082" || echo "PORT_8082_LIBRE"
```

## 9. Checkpoint validé

- Branche : `main`
- Commit : `81f4c04 Add provider rotation smoke runner`
- Profil : `stable-agentic`
- Modèle prioritaire validé : `cloudflare/@cf/moonshotai/kimi-k2.6`
- Conversation Claude Code : validée
- Tool-use Bash non destructif : validé
- État Git après test : propre
- Provider failures observés : `0`

## 10. Sécurité opérationnelle

Ne jamais afficher les clés API en clair. Éviter `cat .env` et `grep API_KEY .env` sans masquage.
Toujours utiliser des guillemets ASCII dans les commandes shell.
