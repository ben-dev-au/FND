"""An index run finishing threw away a search the user was part-way through.

`1f23aec` repaints an open settings screen when a run completes, so a stale
`⚠ nothing indexed` cannot outlive the run that cleared it. `refresh_items`
rebuilds the list from the provider and does not re-apply the row filter, so
four filtered rows became all eight while the box still read the query.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from textual.widgets import Input

from fnd.tui import FNDApp
from fnd.tui.menu import SECTION_PREFERENCES
from fnd.tui.settings_screen import SettingsList, SettingsScreen, open_settings_section
from tests._pilot_wait import settings_ready


async def _filtered(app: FNDApp, pilot: Any, query: str) -> tuple[SettingsScreen, int]:
    open_settings_section(app, SECTION_PREFERENCES)
    await settings_ready(pilot, app)
    screen = app.screen
    assert isinstance(screen, SettingsScreen)
    box = screen.query_one("#settings_search", Input)
    box.value = query
    for _ in range(6):
        await pilot.pause()
    return screen, len(screen.query_one(SettingsList)._items)


@pytest.mark.asyncio
async def test_a_repaint_keeps_the_rows_the_query_narrowed_to(tmp_index_dir: Path) -> None:
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        screen, narrowed = await _filtered(app, pilot, "fuzzy")
        assert narrowed > 0, "precondition: the query matches something"

        screen.refresh_items()
        for _ in range(6):
            await pilot.pause()
        after = len(screen.query_one(SettingsList)._items)
        still_typed = screen.query_one("#settings_search", Input).value

    assert still_typed == "fuzzy", "the box kept the query"
    assert after == narrowed, f"the repaint widened {narrowed} rows to {after}"


@pytest.mark.asyncio
async def test_an_unfiltered_screen_still_gets_the_new_rows(tmp_index_dir: Path) -> None:
    """The control: the repaint exists to pick up a changed set of rows."""
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        open_settings_section(app, SECTION_PREFERENCES)
        await settings_ready(pilot, app)
        screen = app.screen
        assert isinstance(screen, SettingsScreen)
        before = len(screen.query_one(SettingsList)._items)
        screen.refresh_items()
        for _ in range(6):
            await pilot.pause()
        after = len(screen.query_one(SettingsList)._items)

    assert after == before, (before, after)
