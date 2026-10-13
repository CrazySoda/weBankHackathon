"""Prove seed-PDF regeneration is byte-identical.

First run records checksums of every PDF under seed/ into
seed/checksums.sha256 (committed). Later runs after `generate_seed_docs.py`
must reproduce exactly those checksums — any drift fails with a mismatch
report. Run from backend/:  uv run python -I seed/verify_checksums.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "checksums.sha256"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def current() -> list[str]:
    return sorted(
        f"{sha(p)}  {p.relative_to(ROOT).as_posix()}" for p in ROOT.rglob("*.pdf")
    )


def main() -> int:
    now = current()
    if not MANIFEST.exists():
        MANIFEST.write_text("\n".join(now) + "\n")
        print(f"recorded {len(now)} checksums -> {MANIFEST.name}")
        return 0
    expected = MANIFEST.read_text().splitlines()
    if now == expected:
        print(f"identical: {len(now)} PDFs match the recorded manifest")
        return 0
    missing = sorted(set(expected) - set(now))
    added = sorted(set(now) - set(expected))
    print("MISMATCH — regenerated PDFs differ from the committed manifest")
    for line in missing:
        print(f"  - {line.split('  ', 1)[1]}")
    for line in added:
        print(f"  + {line.split('  ', 1)[1]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
