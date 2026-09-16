#!/usr/bin/env python3
"""Challenge 12 — preference profiles + expert lenses (+ auth claim)."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib.prod_client import (  # noqa: E402
    DEFAULT_BASE,
    agent_run,
    request_json,
    write_json,
)

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("CHALLENGE_AGENT_MODEL", "google/gemini-2.5-flash")
SYSTEM = (
    "Ты помощник. Соблюдай блоки предпочтений и призмы в system. "
    "Отвечай строго в запрошенном формате."
)
NAME = "Персонализация · День 12"
QUESTION = (
    "Объясни, зачем нужен буфер обмена в ОС. "
    "Одна короткая мысль + формат по предпочтениям."
)


def _auth_headers(token: str | None) -> dict[str, str]:
    h: dict[str, str] = {}
    if token:
        h["X-Auth-Token"] = token
    return h


def main() -> int:
    base = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")
    print(f"==> challenge 12 personalization @ {base}")
    email = f"day12-{uuid.uuid4().hex[:10]}@example.com"
    password = "challenge12-pass"

    # Register (claim visitor)
    reg = request_json(
        base,
        "/api/v1/auth/register",
        method="POST",
        body={"email": email, "password": password, "display_name": "Day12"},
        timeout=60.0,
    )
    token = str(reg.get("access_token") or "")
    print(f"  registered {email}")

    profiles = request_json(
        base,
        "/api/v1/personalization/profiles",
        timeout=30.0,
        headers=_auth_headers(token),
    )
    by_name = {p["name"]: p for p in profiles if isinstance(p, dict)}
    short_id = (by_name.get("Кратко · JSON") or profiles[0])["id"]
    long_id = (by_name.get("Подробно · Markdown") or profiles[-1])["id"]

    results: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "email": email,
        "runs": {},
    }

    for label, profile_id, lens in (
        ("short_chemist", short_id, "chemist"),
        ("long_economist", long_id, "economist"),
    ):
        request_json(
            base,
            f"/api/v1/personalization/profiles/{profile_id}/activate",
            method="POST",
            body={},
            timeout=30.0,
            headers=_auth_headers(token),
        )
        # agent_run via prod_client does not pass auth yet — extend call
        draft = f"challenge-12-{label}"
        body = {
            "definition": {
                "name": NAME,
                "system_prompt": SYSTEM,
                "preferred_model": MODEL,
                "temperature": 0.2,
                "max_tokens": 220,
            },
            "message": QUESTION,
            "persist": True,
            "client_draft_id": draft,
            "expert_lens_id": lens,
        }
        data = request_json(
            base,
            "/api/v1/agent-workshop/run",
            method="POST",
            body=body,
            timeout=180.0,
            headers=_auth_headers(token),
            retries=1,
        )
        content = str(data.get("content") or "")
        model_id = data.get("model_id")
        print(f"  {label}: {content[:120]!r} · {model_id}")
        results["runs"][label] = {"content": content, "model_id": model_id, "lens": lens}

    short_c = str((results["runs"]["short_chemist"] or {}).get("content") or "")  # type: ignore[index]
    long_c = str((results["runs"]["long_economist"] or {}).get("content") or "")  # type: ignore[index]
    results["checks"] = {
        "answers_differ": short_c.strip() != long_c.strip(),
        "short_has_jsonish": "{" in short_c or "summary" in short_c.lower(),
        "long_has_mdish": "#" in long_c or "-" in long_c or "\n" in long_c,
    }
    write_json(str(HERE / "results.json"), results)
    lines = [
        "# Challenge 12 — Personalization",
        "",
        f"Prod: `{base}` · {results['generated_at']}",
        f"User: `{email}`",
        "",
        "## short_chemist",
        f"- {short_c}",
        "",
        "## long_economist",
        f"- {long_c}",
        "",
        "## Checks",
    ]
    for k, v in results["checks"].items():  # type: ignore[union-attr]
        lines.append(f"- {k}: {'OK' if v else 'FAIL'}")
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  wrote RESULTS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
