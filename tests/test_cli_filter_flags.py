"""CLI filter flags reach the searcher as typed state, not query text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from fnd.cli import app

runner = CliRunner()


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Intercept Searcher.search and record how the CLI called it.

    __init__ is stubbed too: this asserts on argument handling only, and
    opening the real index would couple the test to whatever the developer
    happens to have indexed (and fail outright on a schema-version bump).
    """
    seen: dict[str, Any] = {}

    def fake_search(self: object, query: str, **kwargs: Any) -> list[Any]:
        seen["query"] = query
        seen.update(kwargs)
        return []

    monkeypatch.setattr("fnd.query.Searcher.__init__", lambda self, **kw: None)
    monkeypatch.setattr("fnd.query.Searcher.search", fake_search)
    monkeypatch.setattr("fnd.migrate.prompt_and_rebuild_or_exit", lambda **kw: None)
    return seen


def test_tag_flag_becomes_a_typed_filter(captured: dict[str, Any]) -> None:
    result = runner.invoke(app, ["search", "notes", "--tag", "recipe"])
    assert result.exit_code == 0, result.output
    assert captured["tag_filter"].include["frontmatter"] == frozenset({"recipe"})


def test_tag_flag_is_repeatable(captured: dict[str, Any]) -> None:
    runner.invoke(app, ["search", "notes", "--tag", "a", "--tag", "b"])
    assert captured["tag_filter"].include["frontmatter"] == frozenset({"a", "b"})


def test_not_tag_excludes(captured: dict[str, Any]) -> None:
    runner.invoke(app, ["search", "notes", "--not-tag", "draft"])
    assert captured["tag_filter"].exclude["frontmatter"] == frozenset({"draft"})


def test_tag_match_defaults_to_all(captured: dict[str, Any]) -> None:
    runner.invoke(app, ["search", "notes", "--tag", "a", "--tag", "b"])
    assert captured["tag_filter"].match_all is True


def test_tag_match_any(captured: dict[str, Any]) -> None:
    runner.invoke(app, ["search", "notes", "--tag", "a", "--tag-match", "any"])
    assert captured["tag_filter"].match_all is False


def test_tag_values_are_normalised(captured: dict[str, Any]) -> None:
    """CLI input goes through the same normalisation as indexed tags."""
    runner.invoke(app, ["search", "notes", "--tag", "#Recipe"])
    assert captured["tag_filter"].include["frontmatter"] == frozenset({"recipe"})


def test_hostile_tag_value_never_reaches_the_query(captured: dict[str, Any]) -> None:
    """A shell-supplied hostile value stays a literal in typed state."""
    runner.invoke(app, ["search", "notes", "--tag", 'evil" OR body:x OR "'])
    assert "evil" not in captured["query"]
    values = set().union(*captured["tag_filter"].include.values())
    assert 'evil" or body:x or "' in values


def test_created_flag_becomes_a_query_token(captured: dict[str, Any]) -> None:
    runner.invoke(app, ["search", "notes", "--created", "week"])
    assert "created:week" in captured["query"]


def test_modified_flag_becomes_a_query_token(captured: dict[str, Any]) -> None:
    runner.invoke(app, ["search", "notes", "--modified", "month"])
    assert "mtime:month" in captured["query"]


def test_kind_flag_is_repeatable(captured: dict[str, Any]) -> None:
    runner.invoke(app, ["search", "notes", "--kind", "pdf", "--kind", "md"])
    # Multiple --kind collapse into ONE OR-group so results match ANY of the
    # kinds; separate kind: clauses would AND and match nothing.
    assert "kind:(pdf md)" in captured["query"]


def test_kind_category_flag_expands_to_members(captured: dict[str, Any]) -> None:
    runner.invoke(app, ["search", "notes", "--kind", "code"])
    # A category id expands to an OR-group over its member kinds.
    assert "kind:(" in captured["query"]
    assert "python" in captured["query"]
    assert "cpp" in captured["query"]


def test_parse_filter_flags_expands_categories_for_the_tui_seed() -> None:
    """``parse_filter_flags`` expands category ids to fine-grained kinds in the
    LaunchScope, so the TUI (which seeds ``filter_kinds`` from it) emits
    index-compatible ``kind:`` clauses — a raw ``kind:code`` matches nothing."""
    from fnd.cli import parse_filter_flags
    from fnd.kinds import KINDS_IN_CATEGORY

    scope = parse_filter_flags(
        created=None, modified=None, kind=["code"], tag=[], not_tag=[], tag_match="all"
    )
    assert "code" not in scope.kinds, "category id must be expanded, not passed raw"
    assert set(scope.kinds) == set(KINDS_IN_CATEGORY["code"])
    # De-dup when a category and one of its members are both given.
    scope2 = parse_filter_flags(
        created=None, modified=None, kind=["code", "python"], tag=[], not_tag=[], tag_match="all"
    )
    assert len(scope2.kinds) == len(set(scope2.kinds))


def test_no_flags_passes_no_tag_filter(captured: dict[str, Any]) -> None:
    runner.invoke(app, ["search", "notes"])
    assert captured.get("tag_filter") is None


def test_invalid_date_token_is_rejected(captured: dict[str, Any]) -> None:
    result = runner.invoke(app, ["search", "notes", "--created", "fortnight"])
    assert result.exit_code != 0
    assert "fortnight" in result.output


def test_invalid_tag_match_is_rejected(captured: dict[str, Any]) -> None:
    result = runner.invoke(app, ["search", "notes", "--tag", "a", "--tag-match", "some"])
    assert result.exit_code != 0


class TestTwoFiltersNarrow:
    """The query parser is OR-default, so the TUI space-joining its filter
    clauses made a second filter widen the result set: picking a file type and
    then a date returned files matching either."""

    @staticmethod
    def _index(tmp_path: Path) -> Path:
        from fnd.index import build_index

        src = tmp_path / "src"
        src.mkdir()
        (src / "note.md").write_text("widget widget\n")
        (src / "app.js").write_text("widget in code\n")
        index_dir = tmp_path / "idx"
        index_dir.mkdir()
        build_index(roots=[src], index_dir=index_dir, collection="c")
        return index_dir

    def _names(self, index_dir: Path, query: str) -> set[str]:
        from fnd.query import Searcher

        return {Path(h.path).name for h in Searcher(index_dir=index_dir).search(query, limit=50)}

    def test_two_dimensions_intersect(self, tmp_path: Path) -> None:
        index_dir = self._index(tmp_path)
        assert self._names(index_dir, "(kind:javascript AND kind:md) AND (widget)") == set()

    def test_space_joining_them_would_have_unioned(self, tmp_path: Path) -> None:
        """The negative control: this is the shape the TUI used to build."""
        index_dir = self._index(tmp_path)
        assert self._names(index_dir, "(kind:javascript kind:md) AND (widget)") == {
            "note.md",
            "app.js",
        }

    def test_values_within_one_dimension_still_union(self, tmp_path: Path) -> None:
        index_dir = self._index(tmp_path)
        assert self._names(index_dir, "(kind:(md javascript)) AND (widget)") == {
            "note.md",
            "app.js",
        }


class TestAdHocIndexHonoursTheDefaults:
    """`fnd index <root>` walked ungated while `collection reindex` applied
    `defaults.filters`, so the two commands indexed different file sets — a
    file the configured path excludes could be admitted by the ad-hoc one."""

    @staticmethod
    def _corpus(root: Path) -> None:
        root.mkdir()
        (root / "a.md").write_text("hello\n")
        (root / "b.txt").write_text("hello\n")
        (root / "c.py").write_text("hello\n")

    def test_it_applies_the_default_kinds(self, tmp_path: Path, monkeypatch) -> None:
        from fnd.config import CollectionConfig, DefaultFilters, SourceConfig, resolve_filters
        from fnd.index import build_index_from_config
        from fnd.query import Searcher

        src = tmp_path / "src"
        self._corpus(src)
        defaults = DefaultFilters(kinds=["md"])

        gated = tmp_path / "gated"
        gated.mkdir()
        source = SourceConfig(path=src)
        source._resolved_filters = resolve_filters(source.filters, defaults)
        build_index_from_config(
            config=CollectionConfig(sources=[source]), collection="c", index_dir=gated
        )
        kept = {Path(h.path).name for h in Searcher(index_dir=gated).search("hello", limit=50)}
        assert kept == {"a.md"}, kept

    def test_the_ungated_walk_would_have_taken_everything(self, tmp_path: Path) -> None:
        """The negative control: what the ad-hoc command used to call."""
        from fnd.index import build_index
        from fnd.query import Searcher

        src = tmp_path / "src"
        self._corpus(src)
        raw = tmp_path / "raw"
        raw.mkdir()
        build_index(roots=[src], index_dir=raw, collection="c")
        kept = {Path(h.path).name for h in Searcher(index_dir=raw).search("hello", limit=50)}
        assert kept == {"a.md", "b.txt", "c.py"}, kept
