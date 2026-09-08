"""A picker branch never reads "no rule" for a dimension that has one.

`Maximum file size` cannot hold a minimum and `Modified within` cannot hold an
upper bound, so those bounds live in a second branch. The picker branch went
on painting `○  (Any size)` beside it — the same screen saying both.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from fnd.filters import FilterSpec
from fnd.filters.scan import SourceSample
from fnd.filters.tree_model import spec_branches
from fnd.tui import FNDApp
from fnd.tui.settings_screen import FilterBrowserScreen

_SAMPLE = SourceSample(kinds={"md": 3}, tags={})


def test_a_bound_the_branch_cannot_show_is_still_named_on_it() -> None:
    by_id = {b.id: b for b in spec_branches(FilterSpec(min_size=5_000_000), _SAMPLE)}
    assert by_id["size"].elsewhere == "a minimum is set"

    dated = {
        b.id: b for b in spec_branches(FilterSpec(modified_before=dt.date(2020, 1, 1)), _SAMPLE)
    }
    assert dated["modified"].elsewhere == "an upper bound is set"
    assert not dated["created"].elsewhere, "only the dimension that has one"


def test_an_unbounded_dimension_says_nothing_extra() -> None:
    """The control: the note appears because a rule exists, not always."""
    by_id = {b.id: b for b in spec_branches(FilterSpec(), _SAMPLE)}
    assert not by_id["size"].elsewhere
    assert not by_id["modified"].elsewhere


@pytest.mark.asyncio
async def test_the_row_stops_reading_no_rule(tmp_index_dir: Path) -> None:
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause()
        app.push_screen(
            FilterBrowserScreen(
                title="Index filters",
                spec=FilterSpec(min_size=5_000_000),
                gitignore=True,
                fndignore=True,
                sample_provider=lambda: _SAMPLE,
                on_save=lambda *_a: None,
            )
        )
        for _ in range(25):
            await pilot.pause()
        on_screen = "\n".join(
            "".join(s.text for s in strip) for strip in app.screen._compositor.render_strips()
        )

    row = next(line for line in on_screen.splitlines() if "Maximum file size" in line)
    assert "◐" in row, row
    assert "a minimum is set" in row, row
