"""Media generation domain types (no framework I/O)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass(slots=True)
class MediaArtifact:
    content: bytes
    media_type: str
    extension: str
    provider_label: str


@dataclass(slots=True)
class StoredMedia:
    id: UUID
    media_type: str
    extension: str
    provider_label: str
    public_path: str


@dataclass(slots=True)
class ToolCallRequest:
    """One tool invocation requested by the model or the intent fallback."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


IMAGE_TOOL_NAME = "generate_image"
VIDEO_TOOL_NAME = "generate_video"

MEDIA_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": IMAGE_TOOL_NAME,
            "description": (
                "Generate an image from a text prompt via free Pollinations (flux, sana, or turbo)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Image description in English or Russian.",
                    },
                    "model": {
                        "type": "string",
                        "enum": ["flux", "sana", "turbo"],
                        "description": "Pollinations model id. Default flux.",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": VIDEO_TOOL_NAME,
            "description": "Generate a short free LTX video via Pixazo from a text prompt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Video scene description.",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
]


def parse_tool_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"prompt": str(raw)}
    return parsed if isinstance(parsed, dict) else {"prompt": str(parsed)}


def parse_openai_tool_calls(message: dict[str, Any]) -> list[ToolCallRequest]:
    raw = message.get("tool_calls") or []
    if not isinstance(raw, list):
        return []
    out: list[ToolCallRequest] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fn_raw = item.get("function")
        fn = fn_raw if isinstance(fn_raw, dict) else {}
        name = str(fn.get("name") or "").strip()
        if name not in {IMAGE_TOOL_NAME, VIDEO_TOOL_NAME}:
            continue
        out.append(
            ToolCallRequest(
                id=str(item.get("id") or uuid4()),
                name=name,
                arguments=parse_tool_arguments(fn.get("arguments")),
            )
        )
    return out
