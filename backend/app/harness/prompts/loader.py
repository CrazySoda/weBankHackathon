"""Versioned prompt loading (BUILD_PLAN M4).

Each graph node has a prompt file ``backend/prompts/<node>.md``. Prompts carry
a literal ``{{skills}}`` placeholder that ``app.harness.skills.loader.
render_skills_section`` fills at runtime, plus the untrusted-data rule.

Files are cached by ``(path, mtime)`` so a prompt edit is picked up on the
next run without a restart, and ``prompt_version`` pins the exact prompt text
(a 12-hex sha256 prefix) onto each trace for reproducibility.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# default location of the prompt library (backend/prompts)
DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"

# (path, mtime) -> rendered file text
_cache: dict[tuple[str, float], str] = {}


def prompt_path(prompts_dir: str | Path, node: str) -> Path:
    if not node or "/" in node or node in (".", ".."):
        raise ValueError(f"invalid node name: {node!r}")
    return Path(prompts_dir) / f"{node}.md"


def load_prompt(prompts_dir: str | Path, node: str) -> str:
    """Read ``<prompts_dir>/<node>.md``, cached by (path, mtime).

    Raises ``FileNotFoundError`` for a node without a prompt file.
    """
    path = prompt_path(prompts_dir, node)
    if not path.is_file():
        raise FileNotFoundError(f"no prompt file for node {node!r}: {path}")
    mtime = path.stat().st_mtime
    key = (str(path), mtime)
    if key not in _cache:
        _cache[key] = path.read_text(encoding="utf-8")
    return _cache[key]


def prompt_version(prompts_dir: str | Path, node: str) -> str:
    """First 12 hex chars of the sha256 of the prompt file's content."""
    return hashlib.sha256(load_prompt(prompts_dir, node).encode("utf-8")).hexdigest()[:12]
