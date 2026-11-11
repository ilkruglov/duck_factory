"""Checks that keep the two skill sets in step: Claude Code in plugins/duck-factory, Codex in duck-factory-codex."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = ROOT / "plugins" / "duck-factory" / "skills"
CODEX = ROOT / "plugins" / "duck-factory-codex" / "skills"


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text[text.index("---", 3) + 3 :]


def test_handoff_is_the_same_skill_in_both_harnesses() -> None:
    claude = body(CLAUDE / "handoff" / "SKILL.md").replace("CLAUDE.md", "AGENTS.md")
    assert body(CODEX / "handoff" / "SKILL.md") == claude


def test_codex_skills_do_not_call_claude() -> None:
    for path in CODEX.rglob("*"):
        if path.is_file():
            assert "claude" not in path.read_text(encoding="utf-8").lower(), path


def test_every_codex_skill_has_ui_metadata_and_handoff_is_manual() -> None:
    for skill in ("grill", "review", "handoff"):
        assert (CODEX / skill / "SKILL.md").is_file()
        assert "display_name" in (CODEX / skill / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert "allow_implicit_invocation: false" in (CODEX / "handoff" / "agents" / "openai.yaml").read_text()
    assert "disable-model-invocation: true" in (CLAUDE / "handoff" / "SKILL.md").read_text()


def test_repository_is_english_only() -> None:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for name in files:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search("[\u0400-\u04ff]", text), name
