"""Skill loader tests: manifests, node allowlists, progressive loading."""

from pathlib import Path

import pytest
from app.graph.nodes.plan import AVAILABLE_SKILLS
from app.harness.skills.loader import (
    NODE_TOOL_ALLOWLIST,
    SkillManifest,
    load_manifests,
    load_skill_body,
    render_skills_section,
    skills_for_node,
)

SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"


@pytest.fixture(scope="module")
def manifests() -> dict[str, SkillManifest]:
    return load_manifests(SKILLS_DIR)


def test_manifests_load_for_all_nine_skills(manifests: dict[str, SkillManifest]) -> None:
    assert set(manifests) == set(AVAILABLE_SKILLS)
    assert len(manifests) == 9


def test_names_match_plan_available_skills_exactly(manifests: dict[str, SkillManifest]) -> None:
    assert sorted(manifests) == sorted(AVAILABLE_SKILLS)


def test_every_manifest_node_is_an_allowlist_key(manifests: dict[str, SkillManifest]) -> None:
    for m in manifests.values():
        assert m.node in NODE_TOOL_ALLOWLIST
        assert m.description
        assert m.version
        assert m.body.startswith("## When to use")
        assert "## Method" in m.body
        assert "## Tools & rules" in m.body
        assert "## Output format" in m.body
        assert "## Common pitfalls" in m.body


def test_every_skill_has_rules_and_three_examples(
    manifests: dict[str, SkillManifest],
) -> None:
    for m in manifests.values():
        assert 2 <= len(m.rules.get("rules", [])) <= 4
        for rule in m.rules["rules"]:
            assert set(rule) == {"rule_id", "source_url", "summary"}
            assert rule["source_url"].startswith("http")
        assert len(m.examples) == 6  # 3 input/output pairs


def test_every_skill_tools_within_node_allowlist(
    manifests: dict[str, SkillManifest],
) -> None:
    for m in manifests.values():
        allowed = NODE_TOOL_ALLOWLIST[m.node]
        assert set(m.tools) <= allowed, f"{m.name}: {m.tools} exceeds {m.node} allowlist"


def test_skills_for_node_returns_sorted(manifests: dict[str, SkillManifest]) -> None:
    compliance = skills_for_node(manifests, "compliance")
    assert [m.name for m in compliance] == sorted(m.name for m in compliance)
    assert {m.name for m in compliance} == {
        "lc-ucp600-check",
        "bd-import-docs",
        "cn-export-vat-refund",
        "hs-classification",
        "sanctions-screening",
    }
    assert skills_for_node(manifests, "report") == [manifests["explain-for-sme"]]
    assert skills_for_node(manifests, "intake") == []


def test_load_skill_body_returns_full_manifest(
    manifests: dict[str, SkillManifest],
) -> None:
    m = load_skill_body(manifests, "fx-route-compare", NODE_TOOL_ALLOWLIST["fx"])
    assert m is manifests["fx-route-compare"]
    assert "## Method" in m.body


def test_load_skill_body_rejects_unknown_skill(
    manifests: dict[str, SkillManifest],
) -> None:
    with pytest.raises(ValueError, match="unknown skill"):
        load_skill_body(manifests, "no-such-skill", frozenset({"get_fx_quotes"}))


def test_load_skill_body_rejects_tool_outside_allowlist(
    manifests: dict[str, SkillManifest],
) -> None:
    # fx-route-compare needs get_fx_quotes; the cashflow allowlist lacks it
    with pytest.raises(ValueError, match="outside the node allowlist"):
        load_skill_body(manifests, "fx-route-compare", NODE_TOOL_ALLOWLIST["cashflow"])


def test_load_manifests_rejects_bad_tools_at_load_time(tmp_path: Path) -> None:
    bad = tmp_path / "rogue-skill"
    bad.mkdir()
    fm = "---\nname: rogue-skill\ndescription: tries to act\nnode: verify\nversion: 0.1.0\n---\n"
    (bad / "SKILL.md").write_text(fm + "body\n", encoding="utf-8")
    (bad / "tools.txt").write_text("execute_sandbox_payout\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exceed the 'verify' node allowlist"):
        load_manifests(tmp_path)


def test_render_skills_section_summaries_plus_chosen_bodies(
    manifests: dict[str, SkillManifest],
) -> None:
    node_manifests = skills_for_node(manifests, "fx")
    text = render_skills_section(manifests, "fx", chosen=[m.name for m in node_manifests])
    # one-line summaries for ALL skills of the node
    for m in node_manifests:
        assert f"- {m.name}: {m.description}" in text
    # full body included for chosen skills
    assert "## Method" in text
    # deterministic order: summaries appear sorted
    positions = [text.index(f"- {m.name}:") for m in node_manifests]
    assert positions == sorted(positions)


def test_render_skills_section_unchosen_are_summary_only(
    manifests: dict[str, SkillManifest],
) -> None:
    text = render_skills_section(manifests, "fx", chosen=["fx-route-compare"])
    assert "### Loaded skill: fx-route-compare" in text
    assert "calc_effective_fx_cost, get_fx_quotes" in text  # sorted tools line
    # the only fx skill is chosen; assert a non-chosen node's skill body absent
    other = render_skills_section(manifests, "compliance", chosen=[])
    assert "### Loaded skill:" not in other
    assert "- bd-import-docs:" in other


def test_render_skills_section_empty_node(manifests: dict[str, SkillManifest]) -> None:
    text = render_skills_section(manifests, "intake", chosen=[])
    assert "(none)" in text
