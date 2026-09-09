"""One collection fully ticked beside one partly ticked returned nothing.

`collections` came from FULL collections and `active_sources` from PARTIAL
ones, two disjoint channels, and the query ANDed them: it intersected a
collection name with another collection's source path. The sidebar went on
reading `2/2 active, 3/4 sources` with three sources ticked.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from fnd.config import Config, load
from fnd.index import build_index_from_config
from fnd.query import Searcher


@pytest.fixture
def two_collections(tmp_path: Path, tmp_index_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    vault = tmp_path / "Vault"
    workdocs = tmp_path / "WorkDocs"
    personaldocs = tmp_path / "PersonalDocs"
    for d, marker in (
        (vault, "markervault"),
        (workdocs, "markerwork"),
        (personaldocs, "markerpersonal"),
    ):
        d.mkdir()
        (d / "note.md").write_text(f"# Note\n\nhaystack {marker} here.\n", encoding="utf-8")
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(f"""
            [[collections.Work.sources]]
            path = "{vault.as_posix()}"
            [[collections.Work.sources]]
            path = "{workdocs.as_posix()}"
            [[collections.Personal.sources]]
            path = "{vault.as_posix()}"
            [[collections.Personal.sources]]
            path = "{personaldocs.as_posix()}"
        """),
        encoding="utf-8",
    )
    monkeypatch.setattr("fnd.config.default_config_path", lambda: cfg_path)
    cfg = load(cfg_path)
    # From the CONFIG, not from roots: only this path records `source_path`,
    # which is the field the per-collection source scope filters on.
    for name in ("Work", "Personal"):
        build_index_from_config(
            config=cfg.collections[name], collection=name, index_dir=tmp_index_dir
        )
    return cfg


def _hits(searcher: Searcher, query: str, **kw: object) -> set[str]:
    return {Path(h.path).parent.name for h in searcher.search(query, limit=50, **kw)}  # type: ignore[arg-type]


def test_a_full_collection_survives_beside_a_partial_one(
    two_collections: Config, tmp_path: Path, tmp_index_dir: Path
) -> None:
    """Work whole, Personal reduced to PersonalDocs: both must answer."""
    searcher = Searcher(index_dir=tmp_index_dir)
    personaldocs = str((tmp_path / "PersonalDocs").resolve())

    found = _hits(
        searcher,
        "haystack",
        collection=["Work"],
        source_scope={"Personal": [personaldocs]},
    )

    assert found == {"Vault", "WorkDocs", "PersonalDocs"}, found


def test_a_partial_selection_does_not_reach_the_other_collections_copy(
    two_collections: Config, tmp_path: Path, tmp_index_dir: Path
) -> None:
    """The provenance a flat path list threw away: Vault is in both configs,
    so ticking Personal's copy must not pull Work's chunks into scope."""
    searcher = Searcher(index_dir=tmp_index_dir)
    vault = str((tmp_path / "Vault").resolve())

    found = _hits(searcher, "markerwork", source_scope={"Personal": [vault]})

    assert found == set(), found
