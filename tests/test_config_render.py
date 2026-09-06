"""The canonical config: generated from the models, and what that guarantees."""

from __future__ import annotations

import datetime as dt
import inspect
import tomllib
from pathlib import Path

import pytest
from pydantic import BaseModel

from fnd import config as conf
from fnd.config_migrations import CONFIG_VERSION, ConfigTooNewError, migrate
from fnd.config_render import (
    DEFAULT_GROUPS,
    PRESERVE_BEGIN,
    extract_preserved,
    key,
    path_value,
    render_config,
)


def _models() -> list[tuple[str, type[BaseModel]]]:
    return [
        (n, v)
        for n, v in vars(conf).items()
        if inspect.isclass(v)
        and issubclass(v, BaseModel)
        and v is not BaseModel
        and n != "_ConfigModel"
    ]


def _sample() -> conf.Config:
    return conf.Config(
        # The autouse conftest rewrites two preview defaults but rebuilds only
        # Defaults, not Config, so a nested Defaults still validates with the
        # original. Set them explicitly rather than read a default that differs
        # by construction path.
        defaults=conf.Defaults(
            result_limit=50,
            fuzzy_enabled=False,
            preview_load_debounce_ms=150,
            preview_prefetch_count=4,
        ),
        collections={
            "notes": conf.CollectionConfig(
                sources=[
                    conf.SourceConfig(
                        path=Path("~/Notes"),
                        excludes=["**/.git/**"],
                        app="obsidian",
                        app_params={"vault": "Main"},
                        filters=conf.SourceFilters(kinds=["md"], max_size=50_000_000),
                    )
                ]
            ),
            "Soft Eng Books": conf.CollectionConfig(
                sources=[conf.SourceConfig(path=Path("~/Books"))]
            ),
        },
    )


def _maximal() -> conf.Config:
    """Every non-deprecated field set to something other than its default.

    A sample that sets only the fields the renderer happens to handle proves
    nothing; this one fails the moment a field is added and not rendered.
    """
    filters = {
        "respect_gitignore": False,
        "respect_fndignore": False,
        "include_tags": ["keep"],
        "exclude_tags": ["drop"],
        "kinds": ["md"],
        "min_size": 1,
        "max_size": 50_000_000,
        "created_after": dt.date(2020, 1, 1),
        "created_before": dt.date(2030, 1, 1),
        "modified_after": dt.date(2021, 1, 1),
        "modified_before": dt.date(2031, 1, 1),
        "frontmatter": "Course == 'X'",
        "expression": "file.size > 1",
    }
    return conf.Config(
        defaults=conf.Defaults(
            collection="notes",
            tag_sources=["frontmatter"],
            tag_frontmatter_keys=["Course"],
            result_limit=11,
            preview_chunks=6,
            debounce_ms=201,
            drill_summary_mode="smart",
            sections_score_threshold=0.6,
            sections_per_file_max=201,
            preview_decode_workers=5,
            preview_warm_margin=3,
            preview_load_debounce_ms=151,
            preview_prefetch_count=5,
            fuzzy_enabled=False,
            fuzzy_min_term_chars=4,
            indexer_auto_resume=True,
            cache_at_index_time=False,
            cloud_fetch_timeout_s=61,
            scrollbar_match_highlight=True,
            multicolour_highlights=False,
            preview_scroll_animation=False,
            render_mermaid=False,
            skip_junk_dirs=False,
            extra_junk_dirs=["junk"],
            filters=conf.DefaultFilters(**filters),
        ),
        collections={
            "notes": conf.CollectionConfig(
                sources=[
                    conf.SourceConfig(
                        path=Path("~/Notes"),
                        includes=["**/*.md"],
                        excludes=["**/.git/**"],
                        follow_symlinks=True,
                        filters=conf.SourceFilters(**filters),
                        app="obsidian",
                        app_for={"md": "obsidian"},
                        app_params={"vault": "Main"},
                    )
                ],
                includes=["**/*.md"],
                excludes=["**/tmp/**"],
                follow_symlinks=True,
                ranking_profile="tuned",
            ),
            "Soft Eng Books": conf.CollectionConfig(sources=[]),
        },
        ranking={
            "tuned": conf.RankingProfileConfig(
                recency_boost=0.3,
                recency_half_life="90d",
                filetype_boosts={"md": 1.2},
                phrase_proximity=0.4,
                proximity_max_window=40,
                bm25_k1=1.3,
                bm25_b=0.8,
            )
        },
        apps={
            "obsidian": conf.AppConfig(
                display_name="Obsidian",
                handles=["md"],
                argv=["open", "{path}"],
                notes="a note",
            )
        },
        app_defaults={"md": "obsidian"},
    )


class TestTheWholeSurfaceRoundTrips:
    """The renderer silently dropped every collection-level field until this
    existed — a sample that sets only what the renderer handles cannot fail."""

    def test_the_fixture_really_sets_every_field(self) -> None:
        config = _maximal()
        unset: list[str] = []

        def check(model: BaseModel, label: str, skip: frozenset[str] = frozenset()) -> None:
            for name, info in type(model).model_fields.items():
                # A required field is always set; only an optional one can
                # silently sit at its default and never exercise the renderer.
                if info.deprecated or name in skip or info.is_required():
                    continue
                if getattr(model, name) == info.get_default(call_default_factory=True):
                    unset.append(f"{label}.{name}")

        check(config, "Config")
        check(config.defaults, "Defaults")
        check(config.defaults.filters, "DefaultFilters")
        source = config.collections["notes"].sources[0]
        check(source, "SourceConfig")
        assert source.filters is not None
        check(source.filters, "SourceFilters")
        # roots is the legacy flat shape and cannot coexist with sources.
        check(config.collections["notes"], "CollectionConfig", skip=frozenset({"roots"}))
        check(config.ranking["tuned"], "RankingProfileConfig")
        # argv and url are mutually exclusive, so one must stay unset.
        check(config.apps["obsidian"], "AppConfig", skip=frozenset({"url"}))
        assert not unset, f"fixture leaves fields at their default: {unset}"

    def test_it_survives_a_render(self) -> None:
        config = _maximal()
        assert conf.Config.model_validate(tomllib.loads(render_config(config))) == config

    def test_an_empty_collection_is_not_lost(self) -> None:
        back = conf.Config.model_validate(tomllib.loads(render_config(_maximal())))
        assert "Soft Eng Books" in back.collections
        assert back.collections["Soft Eng Books"].sources == []


class TestDocumentationCannotDrift:
    """The gates that make "every key arrives explained" true, not aspirational."""

    def test_every_field_carries_a_description(self) -> None:
        missing: list[str] = []
        for name, model in _models():
            for field in model.model_fields:
                if not conf.DefaultFilters.model_fields.get(field) and not (
                    model.model_fields[field].description
                ):
                    missing.append(f"{name}.{field}")
        assert not missing, f"undocumented fields reach a user's config: {missing}"

    def test_no_description_is_a_paragraph(self) -> None:
        """A config file wants a line or two per key, not source-comment
        rationale. Long prose belongs in the docs, not in every user's file."""
        long = {
            f"{name}.{field}": len(info.description.split())
            for name, model in _models()
            for field, info in model.model_fields.items()
            if info.description and len(info.description.split()) > 25
        }
        assert not long, f"descriptions too long for a config file: {long}"

    def test_no_generated_prose_uses_an_em_dash(self) -> None:
        """They read as machine-written and the config is user-facing."""
        assert "\u2014" not in conf.starter_config()

    def test_source_filters_borrows_the_defaults_prose(self) -> None:
        """One vocabulary, described once — writing it twice is the duplication
        the renderer exists to remove."""
        rendered = render_config(_sample())
        assert conf.DefaultFilters.model_fields["kinds"].description is not None
        assert "Restrict to these file types" in rendered

    def test_every_default_is_placed_in_exactly_one_group(self) -> None:
        """A field added to Defaults and not grouped would render nowhere."""
        placed = [n for _title, names in DEFAULT_GROUPS for n in names]
        # `filters` renders as its own table, not a key in [defaults].
        assert sorted(placed) == sorted(set(conf.Defaults.model_fields) - {"filters"})
        assert len(placed) == len(set(placed))


class TestRoundTrip:
    def test_a_config_survives_being_rendered(self) -> None:
        config = _sample()
        back = conf.Config.model_validate(tomllib.loads(render_config(config)))
        assert back == config

    def test_rendering_is_idempotent(self) -> None:
        first = render_config(_sample())
        again = conf.Config.model_validate(tomllib.loads(first))
        assert render_config(again) == first

    def test_an_unset_field_renders_as_its_own_example(self) -> None:
        rendered = render_config(_sample())
        assert "# preview_chunks = 5" in rendered

    def test_a_set_field_renders_live(self) -> None:
        assert "\nresult_limit = 50" in render_config(_sample())

    def test_large_numbers_get_digit_separators(self) -> None:
        assert "max_size = 50_000_000" in render_config(_sample())


class TestPortability:
    def test_a_home_path_is_written_back_as_a_tilde(self) -> None:
        """The model expands ~ on load; without re-tilding every generated
        config bakes in one machine's absolute paths."""
        assert path_value(Path.home() / "Notes") == '"~/Notes"'
        assert '"~/Notes"' in render_config(_sample())

    def test_a_path_outside_home_is_left_absolute(self) -> None:
        assert path_value(Path("/opt/corpus")) == '"/opt/corpus"'

    def test_a_collection_name_needing_quotes_gets_them(self) -> None:
        assert key("Soft Eng Books") == '"Soft Eng Books"'
        assert key("notes") == "notes"
        tomllib.loads(render_config(_sample()))  # would raise if unquoted


class TestPreservedBlock:
    def test_the_notes_block_survives_a_write(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(render_config(_sample(), preserved="# my note"), encoding="utf-8")
        conf.write_setting(config_path=path, dotted_path="defaults.result_limit", value=25)
        assert "# my note" in path.read_text(encoding="utf-8")

    def test_text_outside_the_block_does_not_survive(self, tmp_path: Path) -> None:
        """The trade the canonical form makes, stated as a test."""
        path = tmp_path / "config.toml"
        path.write_text(render_config(_sample()) + "\n# stray note\n", encoding="utf-8")
        conf.write_setting(config_path=path, dotted_path="defaults.result_limit", value=25)
        assert "# stray note" not in path.read_text(encoding="utf-8")

    def test_extract_ignores_a_file_without_markers(self) -> None:
        assert extract_preserved("# nothing here\nresult_limit = 5\n") == ""

    def test_the_marker_is_present_even_when_empty(self) -> None:
        assert PRESERVE_BEGIN in render_config(_sample())


class TestMigration:
    def test_a_fresh_config_is_stamped_with_the_current_version(self) -> None:
        raw: dict[str, object] = {}
        version, applied = migrate(raw)
        assert version == CONFIG_VERSION
        assert applied

    def test_a_current_config_needs_nothing(self) -> None:
        assert migrate({"config_version": CONFIG_VERSION}) == (CONFIG_VERSION, [])

    def test_a_newer_config_is_refused_rather_than_silently_stripped(self) -> None:
        with pytest.raises(ConfigTooNewError):
            migrate({"config_version": CONFIG_VERSION + 1})

    def test_the_version_key_never_reaches_the_model(self) -> None:
        """Config forbids unknown keys, so migrate must consume it."""
        raw: dict[str, object] = {"config_version": CONFIG_VERSION}
        migrate(raw)
        assert "config_version" not in raw

    def test_ensure_current_rewrites_a_legacy_file_and_keeps_a_backup(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(
            '[[collections.n.sources]]\npath = "~/Notes"\nfrontmatter_filter = "Course == \'X\'"\n',
            encoding="utf-8",
        )
        applied = conf.ensure_current(path)
        assert applied
        text = path.read_text(encoding="utf-8")
        assert f"config_version = {CONFIG_VERSION}" in text
        assert "\nfrontmatter_filter" not in text, "legacy key kept instead of retired"
        assert "filters]" in text, "the rule should have moved into the filters table"
        assert list(tmp_path.glob("config.toml.bak-*")), "no backup written"

    def test_a_legacy_rule_moves_rather_than_vanishing(self, tmp_path: Path) -> None:
        """The renderer does not advertise a deprecated key, so without the
        transform that moves it the rule is silently deleted on first write."""
        path = tmp_path / "config.toml"
        path.write_text(
            '[[collections.n.sources]]\npath = "~/Notes"\nfrontmatter_filter = "Course == \'X\'"\n',
            encoding="utf-8",
        )
        conf.ensure_current(path)
        source = conf.load(path).collections["n"].sources[0]
        assert source.filters is not None
        assert source.filters.frontmatter == "Course == 'X'"

    def test_a_deprecated_field_still_set_is_written_not_dropped(self) -> None:
        """Fail-safe: a missing migration must not delete a user's rule."""
        config = conf.Config(
            collections={
                "n": conf.CollectionConfig(
                    sources=[
                        conf.SourceConfig(path=Path("~/N"), frontmatter_filter="Course == 'X'")
                    ]
                )
            }
        )
        assert "frontmatter_filter" in render_config(config)

    def test_ensure_current_is_a_no_op_on_a_current_file(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(render_config(_sample()), encoding="utf-8")
        assert conf.ensure_current(path) == []
        assert not list(tmp_path.glob("config.toml.bak-*"))


class TestWritersStayCanonical:
    @pytest.mark.parametrize(
        "write",
        [
            lambda p: conf.write_setting(
                config_path=p, dotted_path="defaults.result_limit", value=7
            ),
            lambda p: conf.write_settings(config_path=p, values={"defaults.debounce_ms": 90}),
            lambda p: conf.write_collection(
                config_path=p,
                name="extra",
                collection=conf.CollectionConfig(sources=[conf.SourceConfig(path=Path("~/E"))]),
            ),
            lambda p: conf.write_collection_source(
                config_path=p,
                collection_name="notes",
                source=conf.SourceConfig(path=Path("~/More")),
            ),
            lambda p: conf.delete_collection(config_path=p, name="notes"),
        ],
    )
    def test_every_writer_leaves_the_file_in_canonical_form(self, write, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(render_config(_sample(), preserved="# kept"), encoding="utf-8")
        write(path)
        text = path.read_text(encoding="utf-8")
        reloaded = conf.load(path)
        assert render_config(reloaded, preserved="# kept") == text
        assert "# kept" in text

    def test_clearing_a_setting_removes_the_key(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(render_config(_sample()), encoding="utf-8")
        conf.write_setting(config_path=path, dotted_path="defaults.result_limit", value=None)
        assert conf.load(path).defaults.result_limit == conf.Defaults().result_limit
