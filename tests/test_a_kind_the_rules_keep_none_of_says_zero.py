"""`Markdown … · 0` was rendered as `Markdown …`, with no number at all.

A rule that matches nothing is the loudest thing the pane can say, and it said
it by falling silent — indistinguishable from `(24 of 40 types)`, where the
counts are deliberately withheld, and from a kind this source simply has none
of. Ground truth at the time: `walk_sources` yielded 0 files and the run had
just reported `0 / 0 files · 11 removed`.
"""

from __future__ import annotations

from fnd.filters.scan import SourceSample
from fnd.filters.tree_model import _kind_items


def _label(items: list[tuple[str, str, str]], kind: str) -> str:
    return next(label for _cat, id_, label in items if id_ == f"kind:{kind}")


def test_a_kind_the_source_has_and_the_rules_drop_reads_zero() -> None:
    sample = SourceSample(kinds={"md": 6}, kinds_kept={}, gated=True)

    label = _label(_kind_items(sample), "md")

    assert label.rstrip().endswith("·  0"), label


def test_a_kind_the_source_does_not_have_carries_no_count() -> None:
    """The control: every kind is offered, so a bare `· 0` on all forty of
    them is a wall of noise that says nothing about this source."""
    sample = SourceSample(kinds={"md": 6}, kinds_kept={"md": 6}, gated=True)

    items = _kind_items(sample)

    assert _label(items, "md").rstrip().endswith("·  6"), _label(items, "md")
    assert "·" not in _label(items, "pdf"), _label(items, "pdf")


def test_an_ungated_sample_is_unchanged() -> None:
    """No gate ran, so there is no "kept none" to report."""
    sample = SourceSample(kinds={"md": 3})

    items = _kind_items(sample)

    assert _label(items, "md").rstrip().endswith("·  3")
    assert "·" not in _label(items, "txt")
