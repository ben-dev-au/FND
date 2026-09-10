"""A bare `▼1` read as one more match, and was off by four.

Measured on a section holding five occurrences with one on screen: the border
said `▼1`, because the four below the fold share a single screenful. The number
was right and the unit was missing, which is also why the same position
reported a different count at a different terminal size.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from fnd.config import Config, load
from fnd.index import build_index
from fnd.tui import FNDApp
from tests._pilot_wait import wait_until


@pytest.fixture
def tall_file(tmp_path: Path, tmp_index_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """One section far taller than any viewport, with several matches in it."""
    root = tmp_path / "notes"
    root.mkdir()
    body = ["# Handbook", "", "## 1. Quorum", ""]
    for i in range(120):
        body.append(f"Filler line {i} carrying no term at all.")
        if i in (10, 40, 70, 100):
            body.append("A quorum is required for this item.")
    (root / "handbook.md").write_text("\n".join(body) + "\n", encoding="utf-8")
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(f"""
            [[collections.notes.sources]]
            path = "{root.as_posix()}"
        """),
        encoding="utf-8",
    )
    monkeypatch.setattr("fnd.config.default_config_path", lambda: cfg_path)
    build_index(roots=[root], index_dir=tmp_index_dir, collection="notes")
    return load(cfg_path)


@pytest.mark.asyncio
async def test_the_border_says_what_it_counted(tall_file: Config, tmp_index_dir: Path) -> None:
    """`screens`, because that is what the number is. Without the unit the
    reader takes it for matches and it is wrong by however many share a
    screenful."""
    app = FNDApp(
        index_dir=tmp_index_dir, config=tall_file, collection="notes", initial_query="quorum"
    )
    async with app.run_test(size=(110, 24)) as pilot:
        await wait_until(
            pilot,
            lambda: bool(app._search.groups),
            timeout=30.0,
            message="the search never produced a result",
        )
        pane: Any = app.query_one("#preview_pane")
        await wait_until(
            pilot,
            lambda: bool(str(pane.border_subtitle or "").strip()),
            timeout=30.0,
            message="the border never carried an indicator",
        )
        subtitle = str(pane.border_subtitle)

    assert "screen" in subtitle, subtitle


def test_the_unit_agrees_with_the_rest_of_the_app() -> None:
    """One plural rule, shared with the results title, so `1 screen` and
    `2 screens` cannot drift apart from `1 file` and `2 files`."""
    from fnd.tui.results_view import _count

    assert _count(1, "", "screen") == "1 screen"
    assert _count(4, "", "screen") == "4 screens"
