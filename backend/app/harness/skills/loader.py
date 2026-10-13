"""Skill manifest loader with progressive disclosure (BUILD_PLAN M4, §7).

A skill is a directory under ``backend/skills/<name>/``::

    SKILL.md      # YAML front-matter (name/description/node/version) + body
    tools.txt     # tool names this skill needs, one per line
    rules.yaml    # curated rules: {rule_id, source_url, summary}
    examples/     # tiny input/output pairs shipped with the skill

Loading model:
  * ``load_manifests`` parses every SKILL.md front-matter once — node prompts
    get name + description summaries only.
  * ``load_skill_body`` returns the full body, but ONLY when the skill's
    ``tools.txt`` fits inside the node's tool allowlist (least privilege,
    rule 0.4). A skill that wants a tool its node may not call is rejected.

Node → tool allowlist mirrors BUILD_PLAN §6 exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# Node -> tool allowlist (BUILD_PLAN §6, verbatim)
# --------------------------------------------------------------------------

NODE_TOOL_ALLOWLIST: dict[str, frozenset[str]] = {
    "plan": frozenset({"lookup_rules"}),
    "compliance": frozenset(
        {
            "lookup_rules",
            "check_lc_documents",
            "suggest_hs_code",
            "screen_sanctions",
            "calc_export_vat_refund",
            "calc_landed_cost",
        }
    ),
    "fx": frozenset({"get_fx_quotes", "calc_effective_fx_cost", "calc_landed_cost"}),
    "cashflow": frozenset({"project_cash_flow", "calc_landed_cost"}),
    "verify": frozenset({"read_source_doc"}),
    "resolve_exception": frozenset({"draft_amendment"}),
    "credit_offer": frozenset({"calc_finance_offer"}),
    "policy_check": frozenset({"evaluate_policy"}),
    "execute": frozenset({"execute_sandbox_payout", "anchor_hash"}),
    "intake": frozenset(),
    "extract_doc": frozenset(),
    "injection_screen": frozenset(),
    "human_approval": frozenset(),
    "escalate": frozenset(),
    "report": frozenset(),
}

# default location of the skill library (backend/skills)
DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"

_SKILL_FILE = "SKILL.md"
_RULE_FILE = "rules.yaml"
_TOOL_FILE = "tools.txt"
_EXAMPLES_DIR = "examples"


@dataclass(frozen=True)
class SkillManifest:
    """Parsed view of one skill directory."""

    name: str
    description: str
    node: str
    version: str
    tools: list[str]  # from tools.txt
    body: str  # SKILL.md body (after the front-matter)
    rules: dict[str, list[dict[str, str]]]  # parsed rules.yaml
    examples: list[str]  # example file contents, sorted by filename


# --------------------------------------------------------------------------
# YAML parsing — pyyaml if the venv happens to carry it, else a minimal
# parser sufficient for our own flat front-matter and rules.yaml shape.
# No new dependency is added either way.
# --------------------------------------------------------------------------

try:  # pragma: no cover - exercised implicitly when pyyaml is present
    import yaml as _yaml
except ImportError:  # pragma: no cover - fallback path
    _yaml = None


def _parse_scalar(value: str) -> str:
    return value.strip().strip("'").strip('"').strip()


def _parse_simple_yaml(text: str) -> dict[str, list[dict[str, str]]]:
    """Minimal parser for::

        key:
          - subkey: value
            subkey2: value2

    (the exact shape of our rules.yaml; good enough as a fallback).
    """
    result: dict[str, list[dict[str, str]]] = {}
    current_key: str | None = None
    current_item: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_key = line[:-1].strip()
            result[current_key] = []
            current_item = None
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and current_key is not None:
            current_item = {}
            result[current_key].append(current_item)
            stripped = stripped[2:]
        if current_item is not None and ":" in stripped:
            k, _, v = stripped.partition(":")
            current_item[k.strip()] = _parse_scalar(v)
    return result


def _load_yaml_mapping(text: str) -> dict[str, list[dict[str, str]]]:
    if _yaml is not None:
        loaded = _yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise ValueError("rules.yaml must contain a top-level mapping")
        return loaded
    return _parse_simple_yaml(text)


def _parse_front_matter(content: str, path: Path) -> tuple[dict[str, str], str]:
    """Split ``---``-delimited front-matter from the body; return (fm, body)."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path}: SKILL.md must start with '---' front-matter")
    end: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError(f"{path}: SKILL.md front-matter is never closed")
    fm_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :]).strip()
    fm: dict[str, str] = {}
    if _yaml is not None:
        loaded = _yaml.safe_load(fm_text)
        if not isinstance(loaded, dict):
            raise ValueError(f"{path}: front-matter must be a mapping")
        fm = {str(k): str(v) for k, v in loaded.items()}
    else:
        for raw in fm_text.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#") or ":" not in raw:
                continue
            k, _, v = raw.partition(":")
            fm[k.strip()] = _parse_scalar(v)
    return fm, body


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_manifests(skills_dir: str | Path = DEFAULT_SKILLS_DIR) -> dict[str, SkillManifest]:
    """Parse every ``<dir>/SKILL.md`` under ``skills_dir``.

    Returns a mapping keyed by skill name. Raises ``ValueError`` on malformed
    skills (missing front-matter keys, unknown node, duplicate names).
    """
    root = Path(skills_dir)
    manifests: dict[str, SkillManifest] = {}
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        skill_md = skill_dir / _SKILL_FILE
        if not skill_md.is_file():
            continue
        fm, body = _parse_front_matter(skill_md.read_text(encoding="utf-8"), skill_md)
        missing = [k for k in ("name", "description", "node", "version") if not fm.get(k)]
        if missing:
            raise ValueError(f"{skill_md}: front-matter missing {missing}")
        name = fm["name"]
        if name != skill_dir.name:
            raise ValueError(
                f"{skill_md}: front-matter name {name!r} != directory {skill_dir.name!r}"
            )
        if fm["node"] not in NODE_TOOL_ALLOWLIST:
            raise ValueError(f"{skill_md}: unknown node {fm['node']!r}")
        if name in manifests:
            raise ValueError(f"{skill_md}: duplicate skill name {name!r}")

        tools = [
            line.strip()
            for line in (skill_dir / _TOOL_FILE).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        unknown = [t for t in tools if t not in NODE_TOOL_ALLOWLIST[fm["node"]]]
        if unknown:
            raise ValueError(
                f"{skill_md}: tools {unknown} exceed the {fm['node']!r} node allowlist"
            )

        rules_file = skill_dir / _RULE_FILE
        rules: dict[str, list[dict[str, str]]] = (
            _load_yaml_mapping(rules_file.read_text(encoding="utf-8"))
            if rules_file.is_file()
            else {}
        )

        examples: list[str] = []
        ex_dir = skill_dir / _EXAMPLES_DIR
        if ex_dir.is_dir():
            examples = [
                p.read_text(encoding="utf-8") for p in sorted(ex_dir.iterdir()) if p.is_file()
            ]

        manifests[name] = SkillManifest(
            name=name,
            description=fm["description"],
            node=fm["node"],
            version=fm["version"],
            tools=tools,
            body=body,
            rules=rules,
            examples=examples,
        )
    return manifests


def skills_for_node(manifests: dict[str, SkillManifest], node: str) -> list[SkillManifest]:
    """Manifests attachable to ``node``, sorted by name (for prompt summaries)."""
    return sorted((m for m in manifests.values() if m.node == node), key=lambda m: m.name)


def load_skill_body(
    manifests: dict[str, SkillManifest], name: str, node_allowlist: frozenset[str]
) -> SkillManifest:
    """Full manifest for a skill named in ``check_plan``.

    Raises ``ValueError`` when the skill is unknown or its ``tools.txt``
    contains a tool outside ``node_allowlist`` — a skill that needs a tool
    the calling node may not use never gets loaded (rule 0.4).
    """
    manifest = manifests.get(name)
    if manifest is None:
        raise ValueError(f"unknown skill: {name!r}")
    exceeding = [t for t in manifest.tools if t not in node_allowlist]
    if exceeding:
        raise ValueError(f"skill {name!r} requires tools {exceeding} outside the node allowlist")
    return manifest


def summary_line(manifest: SkillManifest) -> str:
    """One-line catalogue entry for prompt injection."""
    return f"- {manifest.name}: {manifest.description}"


def render_skills_section(manifests: dict[str, SkillManifest], node: str, chosen: list[str]) -> str:
    """Prompt block for a node: one-line summaries of ALL of the node's
    skills, then the full body of each chosen skill. Deterministic order:
    summaries and bodies are both sorted by skill name."""
    node_manifests = skills_for_node(manifests, node)
    if not node_manifests:
        return f"## Available skills for {node}\n\n(none)\n"

    lines: list[str] = [f"## Available skills for {node}", ""]
    lines += [summary_line(m) for m in node_manifests]

    chosen_set = set(chosen)
    for m in node_manifests:  # sorted; chosen in catalogue order
        if m.name not in chosen_set:
            continue
        lines += ["", f"### Loaded skill: {m.name} (v{m.version})", "", m.body]
        if m.tools:
            lines += ["", "Tools to use: " + ", ".join(sorted(m.tools))]
        rule_ids = sorted(rule.get("rule_id", "") for group in m.rules.values() for rule in group)
        rule_ids = [r for r in rule_ids if r]
        if rule_ids:
            lines += ["Curated rules: " + ", ".join(rule_ids)]
    return "\n".join(lines).strip() + "\n"
