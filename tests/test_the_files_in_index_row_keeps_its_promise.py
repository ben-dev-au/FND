"""`ba75823` said the row "Refreshes when an Update index run finishes".

The row's trailing value comes from the lazy-trailing cache under
`indexing.files_in_index`, and `refresh_items` invalidates seven keys — not
that one. Its 30-second TTL then held the pre-run count, so a sentence I wrote
to replace a true one was false.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fnd.tui import FNDApp
from fnd.tui.menu import SECTION_INDEXING
from fnd.tui.settings_screen import SettingsScreen, open_settings_section
from tests._pilot_wait import settings_ready


@pytest.mark.asyncio
async def test_the_row_is_recomputed_when_a_run_finishes(tmp_index_dir: Path) -> None:
    from fnd.tui import lazy_trailing

    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        open_settings_section(app, SECTION_INDEXING)
        await settings_ready(pilot, app)
        screen = app.screen
        assert isinstance(screen, SettingsScreen)

        # Stand a known value in the cache, as a completed run's own count
        # would be standing there.
        lazy_trailing._CACHE["indexing.files_in_index"] = ("PRERUN-COUNT", 1e18)  # type: ignore[attr-defined]
        screen.refresh_items()
        for _ in range(6):
            await pilot.pause()
        held = lazy_trailing._CACHE.get("indexing.files_in_index")  # type: ignore[attr-defined]

    assert held is None or held[0] != "PRERUN-COUNT", "the run's own count outlived the run"


def test_every_lazy_row_on_the_screen_is_invalidated() -> None:
    """The guard: a row whose value is cached must be in the list that clears
    it, or its description cannot promise a refresh."""
    import inspect
    import re

    from fnd.tui.settings_screen import SettingsScreen

    body = inspect.getsource(SettingsScreen.refresh_items)
    cleared = set(re.findall(r'"([a-z_.]+)"', body))
    menu_src = Path("fnd/tui/menu.py").read_text(encoding="utf-8")
    scheduled = set(re.findall(r'get_or_schedule\(app, "([a-z_.]+)"', menu_src))

    missing = sorted(k for k in scheduled if k.startswith("indexing.") and k not in cleared)
    assert not missing, f"cached rows nothing invalidates: {missing}"
