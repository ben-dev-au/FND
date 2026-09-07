"""tag_sources config field and its write path."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from fnd.config import Config, Defaults, write_setting


def test_defaults_to_both_sources() -> None:
    assert Defaults().tag_sources == ["frontmatter", "os"]


def test_accepts_a_single_source() -> None:
    assert Defaults(tag_sources=["frontmatter"]).tag_sources == ["frontmatter"]


def test_accepts_an_empty_list() -> None:
    """Disabling every source is legitimate: it turns the tag pane off."""
    assert Defaults(tag_sources=[]).tag_sources == []


def test_rejects_an_unknown_source() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        Defaults(tag_sources=["frontmatter", "telepathy"])  # type: ignore[list-item]


def test_round_trips_through_write_setting(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text("", encoding="utf-8")
    updated: Config = write_setting(
        config_path=cfg_path, dotted_path="defaults.tag_sources", value=["frontmatter"]
    )
    assert updated.defaults.tag_sources == ["frontmatter"]
    assert "tag_sources" in cfg_path.read_text(encoding="utf-8")


def test_the_settings_row_offers_the_known_sources_rather_than_free_text() -> None:
    """A closed set of two, typed as prose, was a spelling test."""
    from fnd.tags import TAG_PROVIDERS
    from fnd.tui.menu import KIND_PICKER, _choices_tag_sources, _provider_filters

    row = next(i for i in _provider_filters(None) if i.id == "filters.tag_sources")
    assert row.kind == KIND_PICKER
    assert row.multi
    assert {c.value for c in _choices_tag_sources(None)} == set(TAG_PROVIDERS)


def test_enabling_a_source_needs_a_reindex(tmp_path: Path) -> None:
    """Tags are read when a file is indexed, so the row must not promise that
    turning a source on takes effect immediately."""
    import tantivy

    from fnd.index import build_index
    from fnd.tag_catalogue import tag_catalogue
    from fnd.tui.menu import _provider_filters

    src = tmp_path / "src"
    src.mkdir()
    (src / "n.md").write_text("---\ntags: [alpha]\n---\nhello\n")
    without = tmp_path / "without"
    without.mkdir()
    build_index(roots=[src], index_dir=without, collection="default", tag_sources=("os",))
    catalogue = tag_catalogue(tantivy.Index.open(str(without)), collections=["default"])
    assert catalogue["frontmatter"] == [], "a source off at index time stores no tags"

    row = next(i for i in _provider_filters(None) if i.id == "filters.tag_sources")
    assert "no reindex" not in row.description
