"""Coverage of the filter space itself, rather than of chosen examples.

Three layers, each closed over the schema so a new filter field is included
automatically and fails until it is handled:

* resolution: what a source override does to each field of the defaults;
* behaviour: each field actually changes which files the walker yields;
* invariants: properties that must hold for any combination of filters.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any

import pytest

from fnd.config import CLEARABLE, DefaultFilters, SourceConfig, SourceFilters, resolve_filters
from fnd.walk import walk_sources

#: Per field: a value for the defaults, and a different one for a source to
#: override it with. Every field must appear; the first test enforces that.
VALUES: dict[str, tuple[Any, Any]] = {
    "respect_gitignore": (True, False),
    "respect_fndignore": (True, False),
    "include_tags": (["keep"], ["other"]),
    "exclude_tags": (["drop"], ["nope"]),
    "kinds": (["md"], ["pdf"]),
    "min_size": (10, 20),
    "max_size": (1000, 2000),
    "created_after": (dt.date(2020, 1, 1), dt.date(2021, 1, 1)),
    "created_before": (dt.date(2030, 1, 1), dt.date(2031, 1, 1)),
    "modified_after": (dt.date(2020, 6, 1), dt.date(2021, 6, 1)),
    "modified_before": (dt.date(2030, 6, 1), dt.date(2031, 6, 1)),
    "frontmatter": ("Course == 'A'", "Course == 'B'"),
    "expression": ("file.size > 1", "file.size > 2"),
}

#: Fields whose empty value means "override to nothing", not "unset".
EMPTIABLE = ("include_tags", "exclude_tags", "kinds")


class TestEveryFieldResolves:
    """`resolve_filters` decides what a source actually indexes. Before this,
    seven of the thirteen fields had no override test at all."""

    def test_the_table_covers_every_field(self) -> None:
        """Closed over the schema: a new filter field fails here until it is
        given values, rather than silently going untested. `clears` is not a
        filter but the mechanism for dropping one, and has its own tests."""
        assert set(VALUES) == set(SourceFilters.model_fields) - {"clears"}
        assert set(VALUES) == set(DefaultFilters.model_fields)

    @pytest.mark.parametrize("field", sorted(CLEARABLE))
    def test_a_clearable_field_drops_the_inherited_value(self, field: str) -> None:
        """A list clears with `[]` and a string with `""`; these six had no
        such value, so the choice silently reverted."""
        base, _ = VALUES[field]
        resolved = resolve_filters(
            SourceFilters.model_validate({"clears": [field]}),
            DefaultFilters.model_validate({field: base}),
        )
        assert getattr(resolved, field) is None

    def test_only_the_six_are_clearable(self) -> None:
        """A bool says it with `false` and a list with `[]`; naming those would
        be a second way to say one thing."""
        with pytest.raises(ValueError, match="clears only applies"):
            SourceFilters.model_validate({"clears": ["respect_gitignore"]})

    @pytest.mark.parametrize("field", sorted(VALUES))
    def test_an_unset_field_inherits_the_default(self, field: str) -> None:
        base, _ = VALUES[field]
        defaults = DefaultFilters.model_validate({field: base})
        resolved = resolve_filters(SourceFilters(), defaults)
        assert getattr(resolved, field) == base

    @pytest.mark.parametrize("field", sorted(VALUES))
    def test_a_set_field_overrides_the_default(self, field: str) -> None:
        base, override = VALUES[field]
        defaults = DefaultFilters.model_validate({field: base})
        resolved = resolve_filters(SourceFilters.model_validate({field: override}), defaults)
        assert getattr(resolved, field) == override

    @pytest.mark.parametrize("field", EMPTIABLE)
    def test_an_empty_field_overrides_to_nothing(self, field: str) -> None:
        """`None` inherits and `[]` opts out; conflating them silently keeps a
        rule the user switched off for this source."""
        base, _ = VALUES[field]
        defaults = DefaultFilters.model_validate({field: base})
        resolved = resolve_filters(SourceFilters.model_validate({field: []}), defaults)
        assert not getattr(resolved, field)

    @pytest.mark.parametrize("field", sorted(VALUES))
    def test_resolution_does_not_disturb_other_fields(self, field: str) -> None:
        _, override = VALUES[field]
        defaults = DefaultFilters()
        resolved = resolve_filters(SourceFilters.model_validate({field: override}), defaults)
        for other in VALUES:
            if other != field:
                assert getattr(resolved, other) == getattr(defaults, other), other


def _corpus(root: Path) -> None:
    """A tree where every filter below discriminates: `keep.md` survives each
    filter and `drop.*` is what that filter removes."""
    # Comfortably above min_size and below max_size, so neither bound removes
    # the file every case relies on surviving.
    body = "body here. " * 30
    (root / "keep.md").write_text(f"---\nCourse: A\ntags: [keep]\n---\n{body}\n", encoding="utf-8")
    (root / "drop.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 400)
    (root / "tiny.md").write_text("---\nCourse: A\ntags: [keep]\n---\n", encoding="utf-8")
    (root / "huge.md").write_text(
        "---\nCourse: A\ntags: [keep]\n---\n" + "y" * 5000, encoding="utf-8"
    )
    (root / "other.md").write_text(
        "---\nCourse: B\ntags: [nope]\n---\nbody here\n", encoding="utf-8"
    )
    (root / ".gitignore").write_text("ignored.md\n", encoding="utf-8")
    (root / ".fndignore").write_text("fndignored.md\n", encoding="utf-8")
    for name in ("ignored.md", "fndignored.md"):
        (root / name).write_text("---\nCourse: A\ntags: [keep]\n---\nbody here\n", encoding="utf-8")
    old = dt.datetime(2015, 1, 1).timestamp()
    (root / "old.md").write_text("---\nCourse: A\ntags: [keep]\n---\nbody here\n", encoding="utf-8")
    os.utime(root / "old.md", (old, old))


#: Per field: the value to apply, and the file it must remove from the walk.
#: Tag rules read a note's YAML `tags:`, which works on every platform.
REMOVES: dict[str, tuple[Any, str | None]] = {
    "respect_gitignore": (True, "ignored.md"),
    "respect_fndignore": (True, "fndignored.md"),
    "include_tags": (["keep"], "other.md"),
    "exclude_tags": (["nope"], "other.md"),
    "kinds": (["md"], "drop.pdf"),
    "min_size": (100, "tiny.md"),
    "max_size": (4000, "huge.md"),
    "modified_after": (dt.date(2018, 1, 1), "old.md"),
    "modified_before": (dt.date(2100, 1, 1), None),
    "created_after": (dt.date(1990, 1, 1), None),
    "created_before": (dt.date(2100, 1, 1), None),
    "frontmatter": ("Course == 'A'", "other.md"),
    "expression": ("file.name != 'other.md'", "other.md"),
}


def _walked(root: Path, filters: DefaultFilters, source: SourceFilters | None = None) -> set[str]:
    """Stamps the resolved filters the way Config does. This covers
    `resolve_filters` and the walk; that Config performs the stamping is
    covered by TestConfigStampsResolvedFilters below."""
    src = SourceConfig(path=root, filters=source)
    src._resolved_filters = resolve_filters(source, filters)
    return {p.name for p in walk_sources(sources=[src])}


class TestEveryFieldFilters:
    """Resolution alone proves nothing: a field can resolve correctly and never
    be consulted. Each one must change what the walker yields."""

    def test_the_tables_cover_every_field(self) -> None:
        """Every field is behaviourally tested somewhere: by a real file here,
        or against stubbed timestamps in TestDateFieldsFilter."""
        real = {f for f, (_, removed) in REMOVES.items() if removed}
        assert real | set(DATE_REMOVES) == set(DefaultFilters.model_fields)

    @pytest.mark.parametrize("field", sorted(f for f, (_, r) in REMOVES.items() if r))
    def test_the_default_removes_its_file(self, field: str, tmp_path: Path) -> None:
        _corpus(tmp_path)
        value, removed = REMOVES[field]
        wide = DefaultFilters(respect_gitignore=False, respect_fndignore=False, exclude_tags=[])
        before = _walked(tmp_path, wide)
        after = _walked(tmp_path, wide.model_copy(update={field: value}))
        assert removed in before, f"{removed} was not there to remove"
        assert removed not in after, f"{field} did not remove {removed}"
        assert "keep.md" in after, f"{field} removed the file it should keep"

    @pytest.mark.parametrize("field", sorted(f for f, (_, r) in REMOVES.items() if r))
    def test_a_source_override_reaches_the_walk(self, field: str, tmp_path: Path) -> None:
        """The same rule set on the source, not the defaults."""
        _corpus(tmp_path)
        value, removed = REMOVES[field]
        wide = DefaultFilters(respect_gitignore=False, respect_fndignore=False, exclude_tags=[])
        after = _walked(tmp_path, wide, SourceFilters.model_validate({field: value}))
        assert removed not in after, f"source {field} did not remove {removed}"
        assert "keep.md" in after


class TestInvariantsOverCombinations:
    """Chosen examples cover the cases I thought of. These hold for any
    combination, which is where interaction bugs live."""

    @staticmethod
    def _sets(names: list[str]) -> dict[str, Any]:
        return {n: REMOVES[n][0] for n in names}

    @pytest.mark.parametrize("seed", range(24))
    def test_adding_a_filter_never_yields_more(self, seed: int, tmp_path: Path) -> None:
        """A filter can only remove. If a combination yields a file that a
        subset excluded, two rules are fighting."""
        import random

        rng = random.Random(seed)
        _corpus(tmp_path)
        pool = sorted(f for f, (_, r) in REMOVES.items() if r)
        chosen = rng.sample(pool, rng.randint(1, len(pool)))
        wide = DefaultFilters(respect_gitignore=False, respect_fndignore=False, exclude_tags=[])
        combined = _walked(tmp_path, wide.model_copy(update=self._sets(chosen)))
        for field in chosen:
            alone = _walked(tmp_path, wide.model_copy(update=self._sets([field])))
            assert combined <= alone, f"{chosen} yields what {field} alone excludes"

    @pytest.mark.parametrize("seed", range(24))
    def test_a_combination_removes_every_file_its_parts_remove(
        self, seed: int, tmp_path: Path
    ) -> None:
        """Filters are ANDed, so the combined result is the intersection."""
        import random

        rng = random.Random(seed + 100)
        _corpus(tmp_path)
        pool = sorted(f for f, (_, r) in REMOVES.items() if r)
        chosen = rng.sample(pool, rng.randint(2, len(pool)))
        wide = DefaultFilters(respect_gitignore=False, respect_fndignore=False, exclude_tags=[])
        combined = _walked(tmp_path, wide.model_copy(update=self._sets(chosen)))
        expected = set.intersection(
            *(_walked(tmp_path, wide.model_copy(update=self._sets([f]))) for f in chosen)
        )
        assert combined == expected

    @pytest.mark.parametrize("field", sorted(f for f, (_, r) in REMOVES.items() if r))
    def test_a_source_override_beats_a_stricter_default(self, field: str, tmp_path: Path) -> None:
        """The whole point of per-source filters: one source opting out of a
        rule everything else inherits."""
        _corpus(tmp_path)
        value, removed = REMOVES[field]
        wide = DefaultFilters(respect_gitignore=False, respect_fndignore=False, exclude_tags=[])
        strict = wide.model_copy(update={field: value})
        opted_out = SourceFilters.model_validate({field: _OPT_OUT[field]})
        after = _walked(tmp_path, strict, opted_out)
        assert removed in after, f"source override of {field} did not restore {removed}"

    @pytest.mark.parametrize("seed", range(16))
    def test_order_of_application_does_not_matter(self, seed: int, tmp_path: Path) -> None:
        """AND is commutative; a rule that depends on evaluation order is a bug."""
        import random

        rng = random.Random(seed + 200)
        _corpus(tmp_path)
        pool = sorted(f for f, (_, r) in REMOVES.items() if r)
        chosen = rng.sample(pool, rng.randint(2, len(pool)))
        wide = DefaultFilters(respect_gitignore=False, respect_fndignore=False, exclude_tags=[])
        forward = _walked(tmp_path, wide.model_copy(update=self._sets(chosen)))
        backward = _walked(tmp_path, wide.model_copy(update=self._sets(list(reversed(chosen)))))
        assert forward == backward


#: What a source sets to opt out of the corresponding default.
_OPT_OUT: dict[str, Any] = {
    "respect_gitignore": False,
    "respect_fndignore": False,
    "include_tags": [],
    "exclude_tags": [],
    "kinds": [],
    "min_size": 0,
    "max_size": 10_000_000,
    "modified_after": dt.date(1990, 1, 1),
    "frontmatter": "",
    "expression": "",
}


#: Birth time cannot be set portably, so the date fields are exercised against
#: the same stub the walk reads times through.
DATE_REMOVES: dict[str, tuple[Any, str]] = {
    "created_after": (dt.date(2018, 1, 1), "old.md"),
    "created_before": (dt.date(2025, 1, 1), "future.md"),
    "modified_after": (dt.date(2018, 1, 1), "old.md"),
    "modified_before": (dt.date(2025, 1, 1), "future.md"),
}

_STAMPS = {"old.md": 2015, "future.md": 2035}


class TestDateFieldsFilter:
    """Three of the four date fields had no behavioural test at all: they
    resolved correctly and nothing checked the walk consulted them."""

    @staticmethod
    def _stub(monkeypatch: pytest.MonkeyPatch) -> None:
        from fnd.fsmeta import FileTimes

        def times(path: Path) -> FileTimes:
            year = _STAMPS.get(path.name, 2020)
            stamp = int(dt.datetime(year, 6, 1).timestamp())
            return FileTimes(mtime=stamp, created=stamp, inode_changed=stamp)

        monkeypatch.setattr("fnd.file_facts.read_file_times", times)

    @pytest.mark.parametrize("field", sorted(DATE_REMOVES))
    def test_the_default_removes_its_file(
        self, field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _corpus(tmp_path)
        (tmp_path / "future.md").write_text(
            "---\nCourse: A\ntags: [keep]\n---\nbody here\n", encoding="utf-8"
        )
        self._stub(monkeypatch)
        value, removed = DATE_REMOVES[field]
        wide = DefaultFilters(respect_gitignore=False, respect_fndignore=False, exclude_tags=[])
        before = _walked(tmp_path, wide)
        after = _walked(tmp_path, wide.model_copy(update={field: value}))
        assert removed in before
        assert removed not in after, f"{field} did not remove {removed}"
        assert "keep.md" in after

    @pytest.mark.parametrize("field", sorted(DATE_REMOVES))
    def test_a_source_override_reaches_the_walk(
        self, field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _corpus(tmp_path)
        (tmp_path / "future.md").write_text(
            "---\nCourse: A\ntags: [keep]\n---\nbody here\n", encoding="utf-8"
        )
        self._stub(monkeypatch)
        value, removed = DATE_REMOVES[field]
        wide = DefaultFilters(respect_gitignore=False, respect_fndignore=False, exclude_tags=[])
        after = _walked(tmp_path, wide, SourceFilters.model_validate({field: value}))
        assert removed not in after, f"source {field} did not remove {removed}"
        assert "keep.md" in after


class TestConfigStampsResolvedFilters:
    """`_walked` stamps `_resolved_filters` itself, so on its own it would not
    notice Config failing to. The walk reads only what Config stamped."""

    def test_loading_resolves_each_source_against_the_defaults(self, tmp_path: Path) -> None:
        from fnd.config import Config

        config = Config.model_validate(
            {
                "defaults": {"filters": {"kinds": ["md"], "max_size": 10}},
                "collections": {
                    "c": {
                        "sources": [
                            {"path": str(tmp_path), "filters": {"max_size": 99}},
                            {"path": str(tmp_path)},
                        ]
                    }
                },
            }
        )
        overridden, inherited = config.collections["c"].sources
        assert overridden.effective_filters.max_size == 99
        assert overridden.effective_filters.kinds == ["md"], "defaults were not merged in"
        assert inherited.effective_filters.max_size == 10
