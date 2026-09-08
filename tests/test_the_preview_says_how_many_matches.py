"""Sixteen matches in a table read as "n reaches 2 of 16".

`n` steps between VIEWS — screenfuls holding unseen matches — not between
matches, which is deliberate. On a dense chunk that means it cycles two
screenfuls, and with nothing on screen naming the number of matches it looks
like a two-position toggle. Measured: 16 stops enumerated correctly, 16 known
to the navigator, and the scroll offset alternating 11, 3, 11, 3.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from fnd.config import Config, load
from fnd.index import build_index
from fnd.tui import FNDApp
from fnd.tui.preview_scrollbar import MatchAwareScroll

_TABLE = "| # | Q | A |\n| --- | --- | --- |\n" + "".join(
    f"| {i} | saffron question {i} | answer {i} |\n" for i in range(1, 17)
)


def _corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Config:
    root = tmp_path / "notes"
    root.mkdir()
    (root / "doc.md").write_text(body, encoding="utf-8")
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(f"""
            [[collections.notes.sources]]
            path = "{root.as_posix()}"
        """),
        encoding="utf-8",
    )
    monkeypatch.setattr("fnd.config.default_config_path", lambda: cfg_path)
    return load(cfg_path)


@pytest.mark.asyncio
async def test_a_dense_chunk_names_its_match_count(
    tmp_path: Path, tmp_index_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _corpus(tmp_path, monkeypatch, f"# Table\n\n{_TABLE}\n")
    build_index(roots=[tmp_path / "notes"], index_dir=tmp_index_dir, collection="notes")
    app = FNDApp(index_dir=tmp_index_dir, config=cfg, collection="notes", initial_query="saffron")
    async with app.run_test(size=(100, 20)) as pilot:
        for _ in range(40):
            await pilot.pause()
        pane = app.query_one("#preview_pane", MatchAwareScroll)
        counted = app._match_nav.count
        subtitle = str(pane.border_subtitle)

    assert counted == 16, counted
    assert "16 matches" in subtitle, subtitle


@pytest.mark.asyncio
async def test_a_single_match_stays_quiet(
    tmp_path: Path, tmp_index_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: one match needs no counter, and the border stays clean."""
    cfg = _corpus(tmp_path, monkeypatch, "# One\n\nsaffron appears once.\n")
    build_index(roots=[tmp_path / "notes"], index_dir=tmp_index_dir, collection="notes")
    app = FNDApp(index_dir=tmp_index_dir, config=cfg, collection="notes", initial_query="saffron")
    async with app.run_test(size=(100, 20)) as pilot:
        for _ in range(40):
            await pilot.pause()
        pane = app.query_one("#preview_pane", MatchAwareScroll)
        subtitle = str(pane.border_subtitle)

    assert "matches" not in subtitle, subtitle
