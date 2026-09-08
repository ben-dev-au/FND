"""An empty scope returns nothing, because that is what the panel says.

Unticking every collection painted `Collections · 0/5 active`, every row `○`,
and returned hits from all five: the controller collapsed an empty selection
to None, which the query layer reads as "unscoped". The same dishonesty was
fixed for PARTLY ticked collections and left open on the zero case, with a
test asserting the misleading label.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fnd.config import CollectionConfig, SourceConfig
from fnd.index import build_index_from_config
from fnd.query import Searcher


@pytest.fixture
def two_collections(tmp_path: Path) -> Path:
    index_dir = tmp_path / "idx"
    for name in ("alpha", "beta"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / f"{name}.md").write_text(f"# {name}\n\nzebrafish\n", encoding="utf-8")
        build_index_from_config(
            config=CollectionConfig(sources=[SourceConfig(path=folder)]),
            collection=name,
            index_dir=index_dir,
        )
    return index_dir


def test_no_scope_at_all_searches_everything(two_collections: Path) -> None:
    """The control: None means unscoped, and the CLI relies on it."""
    hits = Searcher(index_dir=two_collections).search("zebrafish", collection=None)
    assert len(hits) == 2


def test_an_explicit_empty_scope_returns_nothing(two_collections: Path) -> None:
    hits = Searcher(index_dir=two_collections).search("zebrafish", collection=[])
    assert hits == []


def test_one_named_collection_still_narrows(two_collections: Path) -> None:
    hits = Searcher(index_dir=two_collections).search("zebrafish", collection=["alpha"])
    assert len(hits) == 1


def test_a_source_scope_without_a_collection_still_works(
    two_collections: Path, tmp_path: Path
) -> None:
    """The near-miss this fix could have caused: a PARTLY ticked collection
    contributes no collection name, and is scoped by source instead. Passing
    the empty list there would return nothing for every partial selection."""
    source = str((tmp_path / "alpha").resolve())
    hits = Searcher(index_dir=two_collections).search(
        "zebrafish", collection=None, active_sources=[source]
    )
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_a_scope_nobody_has_expressed_yet_still_searches(two_collections: Path) -> None:
    """The regression this fix caused, and the distinction it missed.

    An empty selection MAP is not the user unticking everything — it is a
    scope nobody has expressed, which is what a launch looks like before the
    panel populates. Treating the two the same made a fresh app find nothing,
    and only a preview-navigation test noticed.
    """
    from fnd.tui import FNDApp

    app = FNDApp(index_dir=two_collections)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app._scope.selection = {}
        request = app._search._prepare("zebrafish")  # type: ignore[attr-defined]
        scope = request.collection if request is not None else "no request"

    assert scope is None, f"an unexpressed scope must not narrow to nothing: {scope!r}"
