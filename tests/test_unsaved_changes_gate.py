"""Leaving a screen with unsaved work asks before it throws the work away.

Surveyed across all eighteen settings screens: seven lost unsaved work
silently on Esc, one said "discarded" after it was gone, and none prompted.
Esc was the one gesture consistent on all eighteen, and on seven of them it
destroyed work with no signal — so knowing which key saves was a precondition
for not losing data.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from fnd.config import CollectionConfig, Config, SourceConfig
from fnd.tui import FNDApp
from fnd.tui.settings_screen import SourceFormScreen, UnsavedChangesScreen

_MODULE = Path(__file__).resolve().parent.parent / "fnd" / "tui" / "settings_screen.py"


def _app(tmp_path: Path) -> FNDApp:
    corpus = tmp_path / "notes"
    corpus.mkdir(exist_ok=True)
    config = Config(collections={"notes": CollectionConfig(sources=[SourceConfig(path=corpus)])})
    return FNDApp(index_dir=tmp_path / "idx", config=config)


@pytest.mark.asyncio
async def test_a_dirty_form_asks_instead_of_discarding(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.push_screen(SourceFormScreen(collection_name="notes", source_index=0))
        for _ in range(20):
            await pilot.pause()
        form = app.screen
        assert isinstance(form, SourceFormScreen)
        form._fields["excludes_custom"] = "build/**"
        await pilot.press("escape")
        await pilot.pause()
        asked = isinstance(app.screen, UnsavedChangesScreen)

    assert asked, "Esc on a changed form must not leave silently"


@pytest.mark.asyncio
async def test_an_untouched_form_leaves_without_asking(tmp_path: Path) -> None:
    """The control: nothing to lose, nothing to ask about."""
    app = _app(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.push_screen(SourceFormScreen(collection_name="notes", source_index=0))
        for _ in range(20):
            await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        left = not isinstance(app.screen, (SourceFormScreen, UnsavedChangesScreen))

    assert left, "an unchanged form must not stop the user"


@pytest.mark.asyncio
async def test_keep_editing_returns_to_the_form(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.push_screen(SourceFormScreen(collection_name="notes", source_index=0))
        for _ in range(20):
            await pilot.pause()
        form = app.screen
        assert isinstance(form, SourceFormScreen)
        form._fields["excludes_custom"] = "build/**"
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("escape")  # Esc on the prompt = keep editing
        await pilot.pause()
        back_on_form = app.screen is form
        kept = form._fields["excludes_custom"]

    assert back_on_form, "Esc on the prompt must return to the form"
    assert kept == "build/**", "and must not have discarded the edit"


@pytest.mark.asyncio
async def test_discard_leaves_and_drops_the_edit(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.push_screen(SourceFormScreen(collection_name="notes", source_index=0))
        for _ in range(20):
            await pilot.pause()
        form = app.screen
        assert isinstance(form, SourceFormScreen)
        form._fields["excludes_custom"] = "build/**"
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("down", "enter")  # Discard changes
        for _ in range(4):
            await pilot.pause()
        gone = not isinstance(app.screen, (SourceFormScreen, UnsavedChangesScreen))

    assert gone, "Discard must leave the form"


def test_no_editing_screen_leaves_unsaved_work_silently() -> None:
    """Class-wide: a screen that computes dirtiness must route Esc through the
    prompt, so the next editing screen cannot opt out by forgetting."""
    source = _MODULE.read_text(encoding="utf-8")
    offenders: list[str] = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.ClassDef):
            continue
        back = next(
            (
                ast.get_source_segment(source, f) or ""
                for f in node.body
                if isinstance(f, ast.FunctionDef) and f.name == "action_back"
            ),
            "",
        )
        computes_dirty = bool(re.search(r"_dirty\(\)|_snapshot != |_opened_with", back))
        if computes_dirty and "_leave_or_confirm" not in back:
            offenders.append(node.name)
    assert not offenders, f"screens that decide about unsaved work without asking: {offenders}"
