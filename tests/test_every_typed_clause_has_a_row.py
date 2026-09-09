"""A clause typed in the text form and not owned by a picker had no row at all.

Decomposition puts what the pickers cannot render into ``spec.raw``. The tree
named ``spec.expression`` only, so appending a second clause left the screen
showing the first — which a hunter read, reasonably, as a row two edits out of
date.
"""

from __future__ import annotations

from fnd.filters import FilterSpec
from fnd.filters.scan import SourceSample
from fnd.filters.tree_model import spec_branches

_SAMPLE = SourceSample(kinds={"md": 2}, tags={"frontmatter": {"keep": 1}})


def _rows(spec: FilterSpec) -> str:
    return " || ".join(
        f"{b.label} :: {' | '.join(item[1] for item in b.items)}"
        for b in spec_branches(spec, _SAMPLE)
    )


def test_a_raw_clause_is_named_somewhere() -> None:
    spec = FilterSpec(
        expression="file.size < 500000",
        raw=("NOT (file.name ~~ 'scratch-*')", "file.size > 10"),
    )
    rows = _rows(spec)

    assert "scratch-*" in rows, rows
    assert "file.size > 10" in rows, rows


def test_the_count_includes_them() -> None:
    """`(1 set)` over three typed clauses is the same claim in a label."""
    spec = FilterSpec(
        expression="file.size < 500000",
        raw=("NOT (file.name ~~ 'scratch-*')", "file.size > 10"),
    )
    counts = [b.label for b in spec_branches(spec, _SAMPLE) if "(" in b.label]

    assert any("3" in lbl for lbl in counts), counts


def test_enter_on_one_reaches_the_editor_that_owns_it() -> None:
    """No per-field editor can hold a raw clause, so its row hands over."""
    spec = FilterSpec(raw=("file.size > 10",))
    ids = [
        item[0]
        for b in spec_branches(spec, _SAMPLE)
        for item in b.items
        if "file.size > 10" in item[1]
    ]

    assert ids, "no row for it"
    assert all(i.startswith("rule:raw:") for i in ids), ids


def test_a_spec_with_no_raw_clause_says_nothing_extra() -> None:
    """The control: the branch must not appear for a set that has none."""
    rows = _rows(FilterSpec(expression="file.size < 500000"))

    assert "Set in the text form" not in rows, rows
