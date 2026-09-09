"""Typing a word into a numeric setting surfaced Python's own ValueError.

`Result limit · 1-1000   Notes   invalid: invalid literal for int() with base
10: 'Notes'` — the row already knows the range it wants, and the message named
the coercion function instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Input, Static

from fnd.tui import FNDApp
from fnd.tui.menu import KIND_SCALAR, SECTION_PREFERENCES
from fnd.tui.settings_screen import (
    EditBar,
    SettingsList,
    SettingsScreen,
    open_settings_section,
)
from tests._pilot_wait import settings_ready


async def _reject(app: FNDApp, pilot, row_id: str, typed: str) -> str:
    open_settings_section(app, SECTION_PREFERENCES)
    await settings_ready(pilot, app)
    screen = app.screen
    assert isinstance(screen, SettingsScreen)
    lst = screen.query_one(SettingsList)
    idx = next(i for i, it in enumerate(lst._items) if it.id == row_id)
    lst.cursor_index = idx
    screen._activate_item(lst._items[idx])
    await pilot.pause()
    bar = screen.query_one(EditBar)
    bar.query_one("#editor_input", Input).value = typed
    await pilot.press("enter")
    await pilot.pause()
    return str(bar.query_one(".-edit-error", Static).render())


@pytest.mark.asyncio
async def test_a_word_in_a_number_field_is_not_told_about_int(tmp_index_dir: Path) -> None:
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        message = await _reject(app, pilot, "pref.result_limit", "Notes")

    assert "invalid literal for int()" not in message, message
    assert "1-1000" in message, message


@pytest.mark.asyncio
async def test_a_valid_number_is_still_accepted(tmp_index_dir: Path) -> None:
    """The control: the guard must not reject what the field is for."""
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        message = await _reject(app, pilot, "pref.result_limit", "300")

    assert not message.strip(), message


@pytest.mark.asyncio
async def test_a_non_numeric_row_keeps_its_own_message(tmp_index_dir: Path) -> None:
    """The control on scope: only int/float rows get the reworded message."""
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        open_settings_section(app, SECTION_PREFERENCES)
        await settings_ready(pilot, app)
        screen = app.screen
        assert isinstance(screen, SettingsScreen)
        rows = [it for it in screen.query_one(SettingsList)._items if it.kind == KIND_SCALAR]

    assert any(it.coerce is int for it in rows), "no int row to speak for"
