"""Eliding the edit bar's label cut the constraint out of it.

`cbb25fb` stopped the label wrapping over its own field, and capped it at 40%
with an ellipsis. Measured at 110 columns: six of nine numeric rows lost their
range entirely and one rendered `1…`, which does not read as truncated — it
reads as a different range.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from textual.widgets import Input, Static

from fnd.tui import FNDApp
from fnd.tui.menu import KIND_SCALAR, SECTION_PREFERENCES
from fnd.tui.settings_screen import EditBar, SettingsList, SettingsScreen, open_settings_section
from tests._pilot_wait import settings_ready

_RANGE = re.compile(r"^[\d.]+-[\d.]+$")


async def _bar_labels(app: FNDApp, pilot: Any) -> list[tuple[str, str, str]]:
    open_settings_section(app, SECTION_PREFERENCES)
    await settings_ready(pilot, app)
    screen = app.screen
    assert isinstance(screen, SettingsScreen)
    lst = screen.query_one(SettingsList)
    bar = screen.query_one(EditBar)
    out: list[tuple[str, str, str]] = []
    for i, item in enumerate(lst._items):
        if item.kind != KIND_SCALAR or not item.hint:
            continue
        lst.cursor_index = i
        screen._activate_item(item)
        await pilot.pause()
        rows = ["".join(s.text for s in strip) for strip in screen._compositor.render_strips()]
        out.append((item.label, item.hint, next((r for r in rows if "Edit " in r), "")))
        bar.close()
        await pilot.pause()
    return out


@pytest.mark.asyncio
async def test_every_range_survives_the_elision(tmp_index_dir: Path) -> None:
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        seen = await _bar_labels(app, pilot)

    ranges = [(lbl, hint, painted) for lbl, hint, painted in seen if _RANGE.match(hint)]
    assert ranges, "no numeric row to speak for"
    lost = [(lbl, hint) for lbl, hint, painted in ranges if hint not in painted]
    assert not lost, f"the bar states a range it then cuts: {lost}"


@pytest.mark.asyncio
async def test_the_field_keeps_room_to_type_in(tmp_index_dir: Path) -> None:
    """The control on the fix: the cap exists because an uncapped label pushed
    the field off-screen entirely."""
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        open_settings_section(app, SECTION_PREFERENCES)
        await settings_ready(pilot, app)
        screen = app.screen
        assert isinstance(screen, SettingsScreen)
        lst = screen.query_one(SettingsList)
        item = next(it for it in lst._items if it.kind == KIND_SCALAR and it.hint)
        lst.cursor_index = lst._items.index(item)
        screen._activate_item(item)
        await pilot.pause()
        width = screen.query_one("#editor_input", Input).region.width

    assert width >= 12, width


@pytest.mark.asyncio
async def test_a_long_prose_hint_may_still_elide(tmp_index_dir: Path) -> None:
    """Prose degrades to "incomplete"; a range degrades to "wrong". Only the
    second is a defect, and the cap has to stay for the first."""
    from fnd.tui.menu import MenuItem

    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        open_settings_section(app, SECTION_PREFERENCES)
        await settings_ready(pilot, app)
        screen = app.screen
        assert isinstance(screen, SettingsScreen)
        bar = screen.query_one(EditBar)
        long_hint = "'build/**' for a folder; 'build' matches only a file called build"
        bar.open(MenuItem(id="probe", label="Excludes custom globs", hint=long_hint), "")
        await pilot.pause()
        hint_width = bar.query_one(".-edit-hint", Static).region.width
        input_width = screen.query_one("#editor_input", Input).region.width

    assert hint_width < len(long_hint), "an uncapped prose hint is the original defect"
    assert input_width >= 12, input_width
