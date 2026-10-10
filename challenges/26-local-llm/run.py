"""Day 26 prompts and an offline faithfulness score. No network with --score-only."""

from __future__ import annotations

import sys

PROMPTS = {
    "easy": (
        "Запомни на этот ход: имя Артем, язык Python. Ответь ровно двумя строками:\n"
        "Имя: …\nЯзык: …"
    ),
    "medium": "Что такое model_id в ответах ассистента на стенде AIChallenge? Два предложения.",
    "hard": (
        "Куда ходит публичный порт 443 на стенде AIChallenge и можно ли делать "
        "docker compose down на проде? Ответь точно, с портами."
    ),
}


def score(kind: str, text: str) -> int:
    low = text.lower()
    if kind == "easy":
        return 2 if ("артем" in low and "python" in low) else 0
    if kind == "medium":
        surfaces = sum(s in low for s in ("api", "sse", "ui", "db"))
        return 2 if surfaces >= 2 else (1 if "model" in low else 0)
    ports = "443" in text and "8443" in text and "18080" in text
    forbid = any(word in low for word in ("нельзя", "запрещ"))
    if ports and forbid:
        return 2
    if ("8443" in text or "xray" in low) and forbid:
        return 1
    return 0


def main() -> int:
    if "--score-only" in sys.argv:
        assert score("easy", "Имя: Артем\nЯзык: Python") == 2
        assert score("hard", "обычный https. docker compose down --rmi all") == 0
        assert score("hard", "443 идёт в xray, затем nginx :8443. compose down нельзя") == 1
        print("score-only ok")
        return 0
    print("Full run is the recorder: node challenges/record/record-local-llm.mjs")
    print("Graded model: qwen36-fast:latest at http://100.90.210.109:11435")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
