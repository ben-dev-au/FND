"""Clearing is a row you can see in both filter panes, not a key in one.

The sidebar had a focusable `✕ Clear N filters` row; the settings pane cleared
on `c` and showed nothing that said so. A key named in a footer is not an
affordance — nothing on the screen offers it, and Up from the top row reached
nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fnd.filters import FilterSpec
from fnd.filters.scan import SourceSample
from fnd.tui import FNDApp
from fnd.tui.settings_screen import FilterBrowserScreen
from fnd.tui.widgets.clear_bar import ClearFiltersBar
from fnd.tui.widgets.toggle_tree import ToggleTree


def _painted(app: FNDApp) -> str:
    return "\n".join(
        "".join(s.text for s in strip) for strip in app.screen._compositor.render_strips()
    )


_SAMPLE = SourceSample(kinds={"md": 3}, tags={"frontmatter": {"no_index": 1, "keep": 2}})


async def _browser(
    app: FNDApp,
    pilot: object,
    spec: FilterSpec,
    inherited: tuple[FilterSpec, bool, bool] | None = None,
) -> FilterBrowserScreen:
    screen = FilterBrowserScreen(
        title="Index filters",
        spec=spec,
        gitignore=True,
        fndignore=True,
        inherited=inherited,
        sample_provider=lambda: _SAMPLE,
        on_save=lambda *_a: None,
    )
    app.push_screen(screen)
    for _ in range(25):
        await pilot.pause()  # type: ignore[attr-defined]
    return screen


@pytest.mark.asyncio
async def test_the_settings_pane_shows_a_clear_row(tmp_index_dir: Path) -> None:
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        await _browser(app, pilot, FilterSpec(exclude_tags={"frontmatter": ("no_index",)}))
        bar = app.screen.query_one("#clear_filters_bar", ClearFiltersBar)
        visible = bar.visible
        on_screen = _painted(app)

    assert visible, "a set with a rule in it offered no way to clear it"
    assert "Clear all filters" in on_screen, "the row never reached the screen"


@pytest.mark.asyncio
async def test_the_row_names_what_it_does_where_it_inherits(tmp_index_dir: Path) -> None:
    """A source restores what it inherits rather than emptying the set, and
    the row says so — emptying it there would drop the inherited no_index."""
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        await _browser(
            app,
            pilot,
            FilterSpec(kinds=("md",)),
            inherited=(FilterSpec(exclude_tags={"frontmatter": ("no_index",)}), True, True),
        )
        on_screen = _painted(app)

    assert "Reset filters to inherited" in on_screen, on_screen


@pytest.mark.asyncio
async def test_nothing_to_clear_offers_no_row(tmp_index_dir: Path) -> None:
    """The control: the row appears only when pressing it would change
    something, as the sidebar's does."""
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        await _browser(app, pilot, FilterSpec())
        visible = app.screen.query_one("#clear_filters_bar", ClearFiltersBar).visible

    assert not visible


@pytest.mark.asyncio
async def test_up_from_the_top_row_reaches_it(tmp_index_dir: Path) -> None:
    """Arrow keys alone must find it, as they do in the sidebar."""
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        await _browser(app, pilot, FilterSpec(exclude_tags={"frontmatter": ("no_index",)}))
        tree = app.screen.query_one("#filter_tree", ToggleTree)
        tree.focus()
        tree.cursor_line = 0
        for _ in range(4):
            await pilot.pause()
        await pilot.press("up")  # type: ignore[attr-defined]
        for _ in range(4):
            await pilot.pause()
        focused = app.screen.focused

    assert isinstance(focused, ClearFiltersBar), focused


@pytest.mark.asyncio
async def test_enter_on_the_row_clears_and_hands_focus_back(tmp_index_dir: Path) -> None:
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        screen = await _browser(app, pilot, FilterSpec(exclude_tags={"frontmatter": ("no_index",)}))
        bar = app.screen.query_one("#clear_filters_bar", ClearFiltersBar)
        bar.focus()
        for _ in range(4):
            await pilot.pause()
        await pilot.press("enter")  # type: ignore[attr-defined]
        for _ in range(8):
            await pilot.pause()
        spec, focused, visible = screen._spec, app.screen.focused, bar.visible

    assert spec.is_empty(), spec
    assert not visible, "the row stayed after there was nothing left to clear"
    assert isinstance(focused, ToggleTree), focused
