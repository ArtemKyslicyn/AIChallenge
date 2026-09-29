# User Profile — architecture notes

**Spec:** `docs/superpowers/specs/2026-09-29-user-profile-design.md`  
**Stack rules:** `.cursor/skills/aichallenge-architecture` · platform design hexagonal layout

## 1. Boundaries

| Concern | Layer | Notes |
|---|---|---|
| Change password, patch display_name | `domain/auth.py` + `application/auth.py` + `adapters/api/auth.py` | Pure hash/verify in domain; no FastAPI in domain |
| Guest MCP | unchanged ports | Profile **embeds** existing panel; still session-scoped API |
| Model favorites / default | **web-only v1** | `localStorage` key `aichallenge.profile_prefs.v1:<userId>` — no API until sync |
| Global chatPrefs | existing `apps/web/src/chatPrefs/*` | Profile edits same store as ComposerSettings global tab |
| Stand compact status | web client → existing pulse/health APIs | Reuse `LiveModelPulse` / stand probe DTOs; no new MCP routes |
| Personalization active profile | existing `/personalization/*` | Profile shows active + link; CRUD stays Agents |
| Clear local history | web session store only | Must not call destructive server wipe without explicit product decision |

## 2. New API (v1)

```text
PATCH /api/v1/auth/me
  Auth: X-Auth-Token
  Body: { "display_name": string }  # max 120, strip
  → UserMeResponse

POST /api/v1/auth/change-password
  Auth: X-Auth-Token
  Body: { "current_password": string, "new_password": string }
  → 204
  Errors: 400 validation, 401 wrong current / not logged in
```

**Security:** verify current with `verify_password`; `hash_password(new)`; optionally rotate auth token (recommended: revoke current token + mint new, return token like login — product call).  
**Recommendation:** on successful password change, revoke **this** token and return new `AuthTokenResponse` so stolen old token dies; do not revoke all devices in v1 (no list UI yet).

No Alembic change (columns exist).

## 3. Web structure (proposed)

```text
apps/web/src/components/profile/
  ProfilePanel.tsx          # overlay shell, nav, focus trap
  ProfileAccount.tsx
  ProfileSecurity.tsx
  ProfileModels.tsx
  ProfileAnswers.tsx        # wraps global prefs fields
  ProfileChatDefaults.tsx
  ProfileConnections.tsx    # GuestMcpPanel
  ProfileStand.tsx          # compact
  ProfilePersonalization.tsx
  ProfileDevice.tsx
  ProfileAbout.tsx
apps/web/src/profilePrefs.ts  # favorites + defaultModelId per userId
```

`AuthPanel.tsx` becomes entry: opens `ProfilePanel` instead of only popover logout.  
`ComposerSettings`: drop `connections` tab; keep global fields **or** deep-link to profile for global (prefer: global editors live in Profile; composer global tab becomes link — design-lead to confirm density).

## 4. Non-goals (architecture)

- Server-backed chatPrefs table  
- BYOK LLM credentials store  
- Moving Guest MCP registry from session/user scope  
- Email mailer / reset tokens  
- New shell mode in `shellMode.ts`

## 5. Test plan (API)

- Unit: `change_password` wrong current → error; success updates hash  
- Unit: `patch_me` trims display_name  
- API: 401 without token; change-password returns new token if rotation chosen  
- Web: Profile opens, Esc closes; Guest MCP still needs sessionId prop from Chat
