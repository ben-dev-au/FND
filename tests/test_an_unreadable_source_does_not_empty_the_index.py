"""A source folder that exists but cannot be read wiped the collection.

`chmod 000` a source, press Update index, and 48 documents became 0 while the
screen reported `Done. 0 / 0 files`. The walk swallows the PermissionError and
yields nothing; the prune read that silence as "every file was deleted".

The split was exactly inverted: a source that had MOVED AWAY was protected and
did nothing, while a source present but unreadable acted, and destroyed. Same
panel, same word.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from fnd.index import sources_are_enumerable


@pytest.fixture
def unreadable(tmp_path: Path) -> Iterator[Path]:
    """A directory that exists and cannot be listed. Restored so tmp_path can
    be cleaned up even when the assertion fails."""
    d = tmp_path / "locked"
    d.mkdir()
    (d / "note.md").write_text("content\n", encoding="utf-8")
    os.chmod(d, 0o000)
    try:
        yield d
    finally:
        os.chmod(d, stat.S_IRWXU)


def test_an_unreadable_source_is_not_enumerable(unreadable: Path) -> None:
    """The prune is gated on this, and the answer decides whether a mode bit
    can empty a collection."""
    if os.access(unreadable, os.R_OK):
        pytest.skip("running as a user that bypasses directory permissions")

    assert sources_are_enumerable([unreadable]) is False


def test_a_missing_source_is_not_enumerable(tmp_path: Path) -> None:
    """The case that was already protected, kept protected."""
    assert sources_are_enumerable([tmp_path / "gone"]) is False


def test_a_readable_source_is_enumerable(tmp_path: Path) -> None:
    """The control: refusing to prune a healthy source would leave deleted
    files in the index forever."""
    d = tmp_path / "fine"
    d.mkdir()
    (d / "note.md").write_text("content\n", encoding="utf-8")

    assert sources_are_enumerable([d]) is True


def test_an_empty_readable_source_is_still_enumerable(tmp_path: Path) -> None:
    """ "No files" is a real answer and must stay distinguishable from "could
    not look" — emptying a source is how a user removes its files."""
    d = tmp_path / "empty"
    d.mkdir()

    assert sources_are_enumerable([d]) is True


def _indexed_paths(index_dir: Path, collection: str) -> set[str]:
    from fnd.index import indexed_parent_ids
    from fnd.query import _open_index

    index = _open_index(index_dir)
    index.reload()
    return indexed_parent_ids(index, collection)


def test_a_run_over_an_unreadable_source_keeps_the_index(
    tmp_path: Path, tmp_index_dir: Path
) -> None:
    """The hunter's scenario end to end: 2 documents in, mode 000, run again,
    2 documents still there. The guard is only worth having if the run obeys it.
    """
    from fnd.config import CollectionConfig, SourceConfig
    from fnd.index import build_index_from_config

    root = tmp_path / "vault"
    root.mkdir()
    for name in ("a.md", "b.md"):
        (root / name).write_text(f"# {name}\n\nhaystack\n", encoding="utf-8")
    config = CollectionConfig(sources=[SourceConfig(path=root)])
    build_index_from_config(config=config, collection="vault", index_dir=tmp_index_dir)
    before = _indexed_paths(tmp_index_dir, "vault")
    assert len(before) == 2, before

    os.chmod(root, 0o000)
    try:
        if os.access(root, os.R_OK):
            pytest.skip("running as a user that bypasses directory permissions")
        build_index_from_config(config=config, collection="vault", index_dir=tmp_index_dir)
        after = _indexed_paths(tmp_index_dir, "vault")
    finally:
        os.chmod(root, stat.S_IRWXU)

    assert after == before, f"the run emptied the collection: {before} -> {after}"


def test_a_run_over_a_readable_source_still_prunes(tmp_path: Path, tmp_index_dir: Path) -> None:
    """The control: a guard that never lets the prune run would leave deleted
    files searchable forever."""
    from fnd.config import CollectionConfig, SourceConfig
    from fnd.index import build_index_from_config

    root = tmp_path / "vault2"
    root.mkdir()
    for name in ("a.md", "b.md"):
        (root / name).write_text(f"# {name}\n\nhaystack\n", encoding="utf-8")
    config = CollectionConfig(sources=[SourceConfig(path=root)])
    build_index_from_config(config=config, collection="vault2", index_dir=tmp_index_dir)
    assert len(_indexed_paths(tmp_index_dir, "vault2")) == 2

    (root / "b.md").unlink()
    build_index_from_config(config=config, collection="vault2", index_dir=tmp_index_dir)

    assert len(_indexed_paths(tmp_index_dir, "vault2")) == 1
