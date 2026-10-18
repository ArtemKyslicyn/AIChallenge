"""Heuristic rubric (shared with scripts/review) — no LLM required."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SECRET_PATTERNS = [
    (re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[a-z0-9_\-]{16,}"), "possible api key assignment"),
    (re.compile(r"(?i)routerai[_-]?key\s*[:=]\s*['\"]?\S{8,}"), "possible ROUTERAI key"),
    (re.compile(r"(?i)-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----"), "private key block"),
    (re.compile(r"(?i)\.env\b.*\b(PASSWORD|SECRET|TOKEN)\b"), ".env secret reference in diff"),
]

DEPLOY_PATTERNS = [
    (re.compile(r"docker\s+compose\s+down"), "compose down"),
    (re.compile(r"(?i)privateKey|shortIds?\b"), "Reality/xray secret field"),
    (re.compile(r":443\b|:8443\b"), "edge port binding mention — verify loopback-only"),
]

LAYER_PATTERNS = [
    (
        re.compile(r"from\s+app\.adapters\b|import\s+app\.adapters\b"),
        "adapters import — check it is not from domain/",
    ),
]

MODEL_ID_HINT = re.compile(r"model_id|MessageEndEvent|class\s+\w+Event")
MEDICAL = re.compile(r"(?i)\b(patient|doctor|clinic|диагноз|пациент)\b")


@dataclass
class Finding:
    severity: str  # bug | architecture | recommendation
    rule: str
    path: str
    detail: str


@dataclass
class ReviewReport:
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity: str, rule: str, path: str, detail: str) -> None:
        self.findings.append(Finding(severity, rule, path, detail))

    def markdown(self) -> str:
        bugs = [f for f in self.findings if f.severity == "bug"]
        arch = [f for f in self.findings if f.severity == "architecture"]
        recs = [f for f in self.findings if f.severity == "recommendation"]

        def block(title: str, items: list[Finding]) -> str:
            if not items:
                return f"## {title}\n\n_None._\n"
            lines = [f"## {title}\n"]
            for item in items:
                lines.append(f"- **{item.rule}** (`{item.path}`): {item.detail}")
            return "\n".join(lines) + "\n"

        header = "<!-- aichallenge-ai-review -->\n# AIChallenge invariant review\n\n"
        return header + block("Bugs", bugs) + block("Architecture", arch) + block(
            "Recommendations", recs
        )

    @property
    def has_blocking_secrets(self) -> bool:
        return any(f.rule == "secrets" and f.severity == "bug" for f in self.findings)


def _iter_diff_files(diff_text: str) -> list[tuple[str, str]]:
    """Return (path, added_lines) for each file hunk."""
    files: list[tuple[str, str]] = []
    path = ""
    added: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            if path and added:
                files.append((path, "\n".join(added)))
            path = line[6:].strip()
            added = []
        elif line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    if path and added:
        files.append((path, "\n".join(added)))
    return files


def review_diff(diff_text: str) -> ReviewReport:
    report = ReviewReport()
    for path, body in _iter_diff_files(diff_text):
        for rx, detail in SECRET_PATTERNS:
            if rx.search(body):
                report.add("bug", "secrets", path, detail)
        for rx, detail in DEPLOY_PATTERNS:
            if rx.search(body):
                sev = "bug" if "compose down" in detail or "Reality" in detail else "recommendation"
                report.add(sev, "deploy_safety", path, detail)
        if path.startswith("apps/api/src/app/domain/") or "/domain/" in path:
            for rx, detail in LAYER_PATTERNS:
                if rx.search(body):
                    report.add("architecture", "layering", path, detail)
        if ("sse" in path.lower() or "chat" in path.lower()) and "Event" in body:
            if "model_id" not in body and MODEL_ID_HINT.search(body):
                report.add(
                    "recommendation",
                    "model_id",
                    path,
                    "new event/type near SSE — confirm model_id attribution",
                )
        if MEDICAL.search(body):
            report.add("architecture", "domain_names", path, "possible medical naming")
        if path.endswith(".py") and "/tests/" not in path and "test_" not in Path(path).name:
            if "def " in body and "assert " not in body:
                # soft hint only when many new defs
                if body.count("def ") >= 3:
                    report.add(
                        "recommendation",
                        "tests",
                        path,
                        "several new defs — consider unit coverage",
                    )
    return report


def review_paths(paths: list[Path], *, root: Path) -> ReviewReport:
    """Review full file contents (local mode)."""
    chunks: list[str] = []
    for path in paths:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks.append(f"+++ b/{rel}\n" + "\n".join(f"+{line}" for line in text.splitlines()))
    return review_diff("\n".join(chunks))
