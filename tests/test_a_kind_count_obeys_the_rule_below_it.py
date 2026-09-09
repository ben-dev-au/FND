"""`Markdown · 3` sat four lines above `Tags (no_index excluded)`, and the
index held 2.

The count was a raw disk tally while the rule printed under it was the one
that actually ran. This is the audit surface for "did my private files stay
out?", so the number is what gets read.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from fnd.filters import FilterSpec, build_gate
from fnd.filters.dimensions import tag_selection
from fnd.filters.scan import sample_source


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "Vault"
    root.mkdir()
    (root / "meeting-notes.md").write_text("# Meeting\n\nnotes.\n", encoding="utf-8")
    (root / "project-alpha.md").write_text("# Alpha\n\nnotes.\n", encoding="utf-8")
    (root / "salary-review.md").write_text(
        "---\ntags:\n  - no_index\n  - hr\n---\n\n# Salary\n\nprivate.\n", encoding="utf-8"
    )
    return root


def test_the_kept_count_excludes_what_the_tag_rule_removes(tmp_path: Path) -> None:
    """Three markdown files on disk, one tagged `no_index`: the count is 2."""
    root = _vault(tmp_path)
    spec = FilterSpec(exclude_tags=tag_selection({"frontmatter": ["no_index"]}))

    sample = sample_source(root, gate=build_gate(spec))

    assert sample.kinds.get("md") == 3, sample.kinds
    assert sample.kinds_kept.get("md") == 2, sample.kinds_kept


def test_an_unticked_kind_still_reports_what_it_would_bring(tmp_path: Path) -> None:
    """The kind rule is deliberately left out: a kind you have not ticked must
    say how many it would add, not `0`."""
    root = _vault(tmp_path)
    md_only = FilterSpec(kinds=("md",))

    sample = sample_source(root, gate=build_gate(dataclasses.replace(md_only, kinds=())))

    assert sample.kinds_kept.get("md") == 3, sample.kinds_kept


def test_no_gate_leaves_the_kept_count_empty(tmp_path: Path) -> None:
    """The control: without a gate there is nothing to disagree with, and the
    tree falls back to the raw tally."""
    sample = sample_source(_vault(tmp_path))

    assert sample.kinds.get("md") == 3, sample.kinds
    assert sample.kinds_kept == {}, sample.kinds_kept
