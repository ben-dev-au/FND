"""At 100x24 the summary must not restate rows, and the footer must keep the
way out.

Eight rows of content sat under three lines of prose that repeated the row
above them, and the hint bar dropped `Esc/← Discard` from the right — seven
things to do on the screen and no advertised way off it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fnd.filters import FilterSpec
from fnd.filters.scan import SourceSample
from fnd.filters.tree_model import spec_branches
from fnd.tui import FNDApp
from fnd.tui.app import _HintBar
from fnd.tui.settings_screen import FilterBrowserScreen

_SAMPLE = SourceSample(kinds={"md": 3}, tags={"frontmatter": {"no_index": 1}})

_CONTEXTUAL = (
    ("⏎", "Toggle"),
    ("→", "Open"),
    ("/", "Filter"),
    ("t", "As text"),
    ("c", "Clear"),
    ("^s", "Save"),
    ("y", "Copy"),
    ("Esc/←", "Discard"),
)


def test_the_ignore_branch_names_its_own_files() -> None:
    branch = next(b for b in spec_branches(FilterSpec(), _SAMPLE) if b.id == "ignore")
    assert branch.name_leaves, "a two-leaf branch says which, not how many"


def test_a_trimmed_bar_keeps_the_way_out() -> None:
    bar = _HintBar((), _CONTEXTUAL)
    trimmed = bar.fitted(60).plain

    assert "Discard" in trimmed, trimmed
    assert "Save" in trimmed, trimmed
    assert "Copy" not in trimmed, "something optional had to go instead"


def test_the_whole_bar_survives_a_wide_terminal() -> None:
    """The control: nothing is dropped where everything fits."""
    bar = _HintBar((), _CONTEXTUAL)
    full = bar.fitted(400).plain

    for _key, label in _CONTEXTUAL:
        assert label in full, full


@pytest.mark.asyncio
async def test_the_summary_stops_repeating_the_row_above(tmp_index_dir: Path) -> None:
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        app.push_screen(
            FilterBrowserScreen(
                title="Index filters",
                spec=FilterSpec(exclude_tags={"frontmatter": ("no_index",)}),
                gitignore=True,
                fndignore=True,
                sample_provider=lambda: _SAMPLE,
                on_save=lambda *_a: None,
            )
        )
        for _ in range(25):
            await pilot.pause()
        rows = [
            "".join(s.text for s in strip).rstrip()
            for strip in app.screen._compositor.render_strips()
        ]

    branch = next(line for line in rows if "Obey ignore files" in line)
    summary = next(line for line in rows if "skipping hidden files" in line)
    assert ".gitignore, .fndignore" in branch, branch
    assert ".gitignore" not in summary, summary
    assert "Discard" in rows[-1], rows[-1]


class TestTheHeadNamesWhatTheExpressionCannot:
    """Its claim is "what the expression below does NOT cover".

    Trimming it for the narrow terminal took the ignore files out, on the
    grounds that the branch above names them — but the branch says WHICH files
    are obeyed, and this line says THAT they apply at all. Without it the
    expression looked like the whole story, which is the question this line
    exists to answer.
    """

    @pytest.mark.asyncio
    async def test_it_says_ignore_files_apply(self, tmp_index_dir: Path) -> None:
        app = FNDApp(index_dir=tmp_index_dir)
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause()
            app.push_screen(
                FilterBrowserScreen(
                    title="Index filters",
                    spec=FilterSpec(),
                    gitignore=True,
                    fndignore=True,
                    sample_provider=lambda: _SAMPLE,
                    on_save=lambda *_a: None,
                )
            )
            for _ in range(25):
                await pilot.pause()
            rows = [
                "".join(s.text for s in strip).rstrip()
                for strip in app.screen._compositor.render_strips()
            ]

        head = next(line for line in rows if "Outside the expression" in line)
        branch = next(line for line in rows if "Obey ignore files" in line)
        assert "obeying ignore files" in head, head
        assert "skipping hidden files" in head, head
        assert ".gitignore" not in head, "it repeated the row rather than adding to it"
        assert ".gitignore" in branch, "the row stopped naming which"

    @pytest.mark.asyncio
    async def test_it_says_so_when_they_are_off(self, tmp_index_dir: Path) -> None:
        """The control: the claim tracks the setting rather than being decor."""
        app = FNDApp(index_dir=tmp_index_dir)
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause()
            app.push_screen(
                FilterBrowserScreen(
                    title="Index filters",
                    spec=FilterSpec(),
                    gitignore=False,
                    fndignore=False,
                    sample_provider=lambda: _SAMPLE,
                    on_save=lambda *_a: None,
                )
            )
            for _ in range(25):
                await pilot.pause()
            rows = [
                "".join(s.text for s in strip).rstrip()
                for strip in app.screen._compositor.render_strips()
            ]

        head = next(line for line in rows if "Outside the expression" in line)
        assert "ignore files off" in head, head
