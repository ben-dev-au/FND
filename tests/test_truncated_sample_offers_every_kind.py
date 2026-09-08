"""A scan that stopped early narrows nothing.

sample_source stops at 4000 files in walk order, and the picker offered only
what it reached: 4500 notes beside 200 PDFs offered Markdown alone, so "md and
pdf" could not be expressed on that screen at all. Walk order is reverse
alphabetical, so the 4000 are systematically the last 4000 — a year-foldered
corpus loses its earliest years from every picker.
"""

from __future__ import annotations

from fnd.filters import FilterSpec
from fnd.filters.scan import SourceSample
from fnd.filters.tree_model import spec_branches
from fnd.kinds import ALL_KIND_IDS


def _offered(sample: SourceSample, spec: FilterSpec | None = None) -> set[str]:
    branches = spec_branches(spec or FilterSpec(), sample)
    kinds = next((b for b in branches if b.id == "kinds"), None)
    assert kinds is not None
    return {i.removeprefix("kind:") for g in kinds.groups for i, _label in g.items}


def test_a_truncated_scan_offers_every_kind() -> None:
    seen_only_md = SourceSample(kinds={"md": 4000}, tags={}, truncated=True)
    assert _offered(seen_only_md) == set(ALL_KIND_IDS)


def test_a_complete_scan_still_narrows() -> None:
    """The control: a scan that reached the end is evidence, and the short
    relevant list is the whole point of sampling."""
    whole_source = SourceSample(kinds={"md": 3}, tags={}, truncated=False)
    assert _offered(whole_source) == {"md"}


def test_a_configured_kind_survives_either_way() -> None:
    spec = FilterSpec(kinds=("pdf",))
    for truncated in (True, False):
        sample = SourceSample(kinds={"md": 3}, tags={}, truncated=truncated)
        assert "pdf" in _offered(sample, spec), truncated


def test_a_truncated_branch_may_claim_every_type() -> None:
    """With every kind offered, ticking them all really is "every type"."""
    sample = SourceSample(kinds={"md": 4000}, tags={}, truncated=True)
    kinds = next(b for b in spec_branches(FilterSpec(), sample) if b.id == "kinds")
    assert kinds.full_label == "every type"
