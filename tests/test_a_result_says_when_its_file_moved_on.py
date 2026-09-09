"""The preview rendered a deleted file in full, unmarked.

Searching for a word that only ever appeared in a file deleted a week ago
returned one result and a full-fidelity preview titled with the missing file's
name. Worse for an edited file: the file still exists, so a user who opens it
sees different text from the one just shown, with no explanation. The preview
is served from the index's stored body, so it is a photograph presented as a
live view.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from textual.widgets import Tree

from fnd.config import Config, load
from fnd.index import build_index
from fnd.query import FileGroup, Hit
from fnd.tui import FNDApp
from fnd.tui.results_labels import is_stale


def _group(path: Path, indexed_mtime: int) -> FileGroup:
    hit = Hit(
        score=1.0,
        parent_id="p",
        path=str(path),
        kind="md",
        page=0,
        slide=0,
        heading_path="",
        title="",
        snippet="",
        page_label="",
        chunk_seq=0,
        line=0,
        mtime=indexed_mtime,
        pass_index=0,
        meta_blob=b"",
        body_text="",
        body_md="",
    )
    return FileGroup(parent_id="p", path=str(path), kind="md", title="", top_score=1.0, hits=[hit])


def test_a_file_that_is_gone_is_stale(tmp_path: Path) -> None:
    """`read_file_times` gives zeros for a vanished file, which is the answer."""
    missing = tmp_path / "deleted.md"

    assert is_stale(_group(missing, 1_000_000)) is True


def test_a_file_edited_since_indexing_is_stale(tmp_path: Path) -> None:
    """The file exists, which is what makes this the worse case: the user opens
    it and sees text the app never showed them."""
    live = tmp_path / "edited.md"
    live.write_text("now\n", encoding="utf-8")
    indexed_before = int(live.stat().st_mtime) - 60

    assert is_stale(_group(live, indexed_before)) is True


def test_an_unchanged_file_is_not_stale(tmp_path: Path) -> None:
    """The control: marking a live row would train the user to ignore it."""
    live = tmp_path / "same.md"
    live.write_text("now\n", encoding="utf-8")
    indexed_now = int(live.stat().st_mtime) + 5

    assert is_stale(_group(live, indexed_now)) is False


@pytest.fixture
def indexed(tmp_path: Path, tmp_index_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    root = tmp_path / "notes"
    root.mkdir()
    (root / "keep.md").write_text("# Keep\n\nsnickersnee here.\n", encoding="utf-8")
    (root / "vanish.md").write_text("# Vanish\n\nsnickersnee here too.\n", encoding="utf-8")
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
async def test_the_row_of_a_deleted_file_is_marked(
    indexed: Config, tmp_path: Path, tmp_index_dir: Path
) -> None:
    """End to end: index two files, delete one, search without reindexing."""
    (tmp_path / "notes" / "vanish.md").unlink()

    app = FNDApp(
        index_dir=tmp_index_dir, config=indexed, collection="notes", initial_query="snickersnee"
    )
    async with app.run_test(size=(110, 30)) as pilot:
        for _ in range(30):
            await pilot.pause()
        tree = app.query_one("#results_pane", Tree)
        labels = {str(node.label) for node in tree.root.children}

    gone = [label for label in labels if "vanish" in label]
    kept = [label for label in labels if "keep" in label]
    assert gone, labels
    assert kept, labels
    assert all("⚠" in label for label in gone), gone
    assert not any("⚠" in label for label in kept), kept
