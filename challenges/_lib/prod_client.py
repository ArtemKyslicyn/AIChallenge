"""Shared prod helpers for challenge runners (no third-party deps)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE = "https://aichallenge.arcilite.ru"
VISITOR = "aichallenge-challenge-runner"


def estimate_tokens(text: str) -> int:
    t = text.strip()
    if not t:
        return 0
    return max(1, round(len(t) / 4))


def estimate_cost_proxy(model_id: str | None) -> float:
    if not model_id:
        return 1.0
    mid = model_id.lower()
    if ":free" in mid or mid.endswith("/free") or "openrouter/free" in mid:
        return 0.05
    if any(x in mid for x in ("nano", "mini", "flash", "haiku")):
        return 0.4
    if any(x in mid for x in ("235b", "ultra", "opus", "gpt-4", "o1", "o3")):
        return 3.0
    if any(x in mid for x in ("v3.2", "v3", "sonnet", "pro")):
        return 1.6
    return 1.0


def request_json(
    base: str,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 120.0,
    retries: int = 2,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            f"{base.rstrip('/')}{path}",
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Visitor-Id": VISITOR,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"HTTP {exc.code} {path}: {detail[:400]}")
            if attempt < retries and exc.code in {429, 502, 503}:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last_err from exc
        except TimeoutError as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    assert last_err is not None
    raise last_err


def probe(
    base: str,
    prompt: str,
    *,
    model: str | None = None,
    models: list[str] | None = None,
    temperature: float | None = None,
    reasoning: bool | None = False,
    timeout: float = 120.0,
) -> dict[str, Any]:
    candidates: list[str | None]
    if models:
        candidates = list(models)
    elif model:
        candidates = [model]
    else:
        candidates = [None]

    errors: list[str] = []
    for candidate in candidates:
        payload: dict[str, Any] = {"prompt": prompt, "stream": False}
        if candidate:
            payload["model"] = candidate
        if temperature is not None:
            payload["temperature"] = temperature
        if reasoning is not None:
            payload["reasoning"] = reasoning
        t0 = time.perf_counter()
        try:
            data = request_json(
                base,
                "/api/v1/llm/complete",
                method="POST",
                body=payload,
                timeout=timeout,
                retries=1,
            )
        except Exception as exc:  # noqa: BLE001 — collect and try next model
            errors.append(f"{candidate or 'auto'}: {exc}")
            continue
        latency_ms = int((time.perf_counter() - t0) * 1000)
        content = str(data.get("content") or "")
        model_id = data.get("model_id")
        # Reject obvious content-safety stubs
        if "content-safety" in str(model_id or "").lower() and len(content.strip()) < 40:
            errors.append(f"{model_id}: stub/safety response")
            continue
        return {
            "content": content,
            "model_id": model_id,
            "requested_model": candidate,
            "latency_ms": latency_ms,
            "tokens_approx": estimate_tokens(content),
            "cost_proxy": estimate_cost_proxy(str(model_id) if model_id else None),
        }
    raise RuntimeError("All probe candidates failed: " + " | ".join(errors[:4]))


def list_models(base: str) -> list[dict[str, Any]]:
    data = request_json(base, "/api/v1/llm/models", timeout=30.0)
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected models payload: {data!r}")
    return data


def pick_tiers(model_ids: list[str]) -> dict[str, str]:
    def ok(mid: str) -> bool:
        if not mid or mid == "auto":
            return False
        low = mid.lower()
        if "content-safety" in low:
            return False
        if mid in {"openrouter/free"}:
            return False
        return True

    usable = [m for m in model_ids if ok(m)]
    if not usable:
        usable = [m for m in model_ids if m and m != "auto"]
    if not usable:
        return {"weak": "auto", "mid": "auto", "strong": "auto"}
    if len(usable) == 1:
        return {"weak": usable[0], "mid": usable[0], "strong": usable[0]}
    if len(usable) == 2:
        return {"weak": usable[0], "mid": usable[1], "strong": usable[1]}
    mid = (len(usable) - 1) // 2
    return {"weak": usable[0], "mid": usable[mid], "strong": usable[-1]}


def write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
