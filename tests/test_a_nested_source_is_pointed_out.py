"""Adding a source inside another was accepted in silence.

A hunter added an overlapping nested source deliberately, confirmed the index
deduplicated it (11 docs, not 12), and noted that nothing in the app had said
so. It is harmless and it is also pointless — a source that indexes nothing new
reads exactly like one that does.
"""

from __future__ import annotations

from pathlib import Path

from fnd.config import SourceConfig
from fnd.tui.settings_screen import _overlapping_source


def _src(path: Path) -> SourceConfig:
    return SourceConfig(path=path)


def test_a_child_of_an_existing_source_is_named(tmp_path: Path) -> None:
    parent = tmp_path / "vault"
    (parent / "notes").mkdir(parents=True)

    found = _overlapping_source([_src(parent)], _src(parent / "notes"), None)

    assert found == str(parent)


def test_a_parent_of_an_existing_source_is_named(tmp_path: Path) -> None:
    """The other direction: the new source swallows one already there."""
    parent = tmp_path / "vault"
    (parent / "notes").mkdir(parents=True)

    found = _overlapping_source([_src(parent / "notes")], _src(parent), None)

    assert found == str(parent / "notes")


def test_the_same_folder_twice_is_named(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()

    assert _overlapping_source([_src(root)], _src(root), None)


def test_a_sibling_is_not(tmp_path: Path) -> None:
    """The control: two unrelated folders must say nothing."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    assert not _overlapping_source([_src(tmp_path / "a")], _src(tmp_path / "b"), None)


def test_editing_a_source_does_not_flag_itself(tmp_path: Path) -> None:
    """The trap: the row being edited is still in the list it is compared to."""
    root = tmp_path / "vault"
    root.mkdir()

    assert not _overlapping_source([_src(root)], _src(root), 0)


def test_a_missing_folder_is_not_a_crash(tmp_path: Path) -> None:
    """Paths are resolved, and a source can name a folder that is not there."""
    assert not _overlapping_source([_src(tmp_path / "gone")], _src(tmp_path / "also-gone"), None)
