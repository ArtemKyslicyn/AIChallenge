---
name: aichallenge-secrets
description: >-
  Secret and .env safety for AIChallenge and Cursor Cloud. Use whenever
  touching env files, Docker Compose, CI secrets, API keys, DATABASE_URL,
  LLM_API_KEY, or when the user mentions credentials.
---

# AIChallenge Secrets

## Hard rules

- **Never** read, open, cat, or quote `.env` (or any file with real secret values).
- **Never** paste secret values into chat, commits, Dockerfiles, README, or specs.
- Discuss **variable names only** (e.g. `LLM_API_KEY`), never values.
- Commit only `.env.example` with empty or obviously fake placeholders.
- Cursor Cloud / CI: inject via secrets store → process env. Not via prompts.

## Allowed files

| File | In git? | Contents |
|------|---------|----------|
| `.env.example` | yes | names + empty/`changeme` |
| `.env` | **no** | local secrets |
| Compose `env_file: .env` | path only | values stay local |

## If a secret appears in chat or diff

1. Stop echoing it.
2. Tell the user to rotate the key.
3. Do not write it into any tracked file.

## Agent checklist before commit

- [ ] No `.env` staged
- [ ] No `sk-`, bearer tokens, or connection strings with passwords in diff
- [ ] `.gitignore` / `.cursorignore` still cover `.env`, `*.pem`
