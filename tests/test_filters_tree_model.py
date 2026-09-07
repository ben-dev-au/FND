"""The filter set as tree branches, and back — the model behind the browser."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path

import pytest

from fnd.filters import FilterSpec
from fnd.filters.scan import SourceSample, sample_source
from fnd.filters.tree_model import (
    Branch,
    apply_selection,
    custom_ids,
    selection_for,
    spec_branches,
)


def _leaves(branches: list[Branch]) -> set[str]:
    """Every item id at any depth — kinds now sit under one File types parent."""
    out: set[str] = set()
    stack = list(branches)
    while stack:
        b = stack.pop()
        out |= {i[0] for i in b.items}
        stack.extend(b.groups)
    return out


def _sample() -> SourceSample:
    return SourceSample(
        kinds={"md": 439, "pdf": 7},
        tags={"os": {"no_index": 3, "wk3": 2}, "frontmatter": {"private": 15}},
    )


class TestBranches:
    def test_only_kinds_present_are_offered(self) -> None:
        """A picker listing types the source does not contain is noise."""
        found = {
            i for i in _leaves(spec_branches(FilterSpec(), _sample())) if i.startswith("kind:")
        }
        assert found == {"kind:md", "kind:pdf"}

    def test_every_kind_is_offered_when_nothing_is_known(self) -> None:
        kinds = {i for i in _leaves(spec_branches(FilterSpec(), None)) if i.startswith("kind:")}
        assert len(kinds) > 10

    def test_file_types_hang_off_one_parent(self) -> None:
        """Seven loose 'File type · X' siblings read as seven unrelated filters."""
        branches = spec_branches(FilterSpec(), None)
        tops = [b for b in branches if b.id == "kinds"]
        assert len(tops) == 1
        assert tops[0].label == "File types"
        assert not tops[0].items, "categories belong under the parent, not beside it"
        assert len(tops[0].groups) > 3

    def test_the_file_type_branch_says_what_empty_means(self) -> None:
        """Nothing ticked means every type, which ○ alone reads as the opposite."""
        kinds = next(b for b in spec_branches(FilterSpec(), None) if b.id == "kinds")
        assert kinds.empty_label == "every type"

    def test_tag_branch_cycles_and_others_do_not(self) -> None:
        modes = {b.id: b.mode for b in spec_branches(FilterSpec(), _sample())}
        assert modes["tags"] == "cycle"
        assert modes["ignore"] == "multi"
        assert modes["size"] == "radio"

    def test_an_active_tag_sorts_first(
        self,
    ) -> None:
        """What is switched on must be visible without scrolling the corpus."""
        spec = FilterSpec(exclude_tags={"os": ("wk3",)})
        tags = next(b for b in spec_branches(spec, _sample()) if b.id == "tags")
        os_group = next(g for g in tags.groups if g.id == "tags:os")
        assert os_group.items[0][0] == "tag:os:wk3"

    def test_a_tag_in_both_sources_gets_a_row_in_each(self) -> None:
        """A Finder tag and a note tag sharing a word are different rules."""
        sample = SourceSample(tags={"os": {"draft": 2}, "frontmatter": {"draft": 5}})
        tags = next(b for b in spec_branches(FilterSpec(), sample) if b.id == "tags")
        by_source = {b.id: [i[0] for i in b.items] for b in tags.groups}
        assert by_source == {
            "tags:os": ["tag:os:draft"],
            "tags:frontmatter": ["tag:frontmatter:draft"],
        }

    def test_one_source_needs_no_extra_level(self) -> None:
        """Nesting a lone source under a parent is a click for nothing."""
        sample = SourceSample(tags={"frontmatter": {"draft": 5}})
        tags = next(b for b in spec_branches(FilterSpec(), sample) if b.id == "tags")
        assert not tags.groups
        assert [i[0] for i in tags.items] == ["tag:frontmatter:draft"]

    def test_a_configured_tag_absent_from_the_sample_still_appears(self) -> None:
        spec = FilterSpec(exclude_tags={"os": ("never_scanned",)})
        tags = next(b for b in spec_branches(spec, _sample()) if b.id == "tags")
        os_group = next(g for g in tags.groups if g.id == "tags:os")
        assert any(i[0] == "tag:os:never_scanned" for i in os_group.items)


class TestSelectionRoundTrip:
    @pytest.mark.parametrize(
        "spec",
        [
            FilterSpec(),
            FilterSpec(exclude_tags=("no_index",)),
            FilterSpec(kinds=("md", "pdf")),
            FilterSpec(max_size=50_000_000),
            FilterSpec(kinds=("md",), exclude_tags=("no_index",), max_size=1_000_000),
        ],
    )
    def test_a_spec_survives_the_tree(self, spec: FilterSpec) -> None:
        selected, excluded = selection_for(spec, gitignore=True, fndignore=False)
        back, git, fnd = apply_selection(spec, selected, excluded)
        assert back == spec
        assert git is True
        assert fnd is False

    def test_a_date_window_resolves_to_a_fixed_bound(self) -> None:
        """A rolling window would change what the index holds as time passes."""
        spec, _git, _fnd = apply_selection(FilterSpec(), {"modified:30"}, set())
        assert spec.modified_after == dt.date.today() - dt.timedelta(days=30)

    def test_choosing_any_clears_the_bound(self) -> None:
        start = FilterSpec(max_size=50_000_000)
        spec, _g, _f = apply_selection(start, {"size:any"}, set())
        assert spec.max_size is None

    def test_the_expression_is_left_alone(self) -> None:
        """The tree edits the rows; anything it cannot show must survive."""
        start = FilterSpec(expression="file.name ~~ 'draft-*'", frontmatter="Course == 'X'")
        spec, _g, _f = apply_selection(start, {"size:any"}, set())
        assert spec.expression == "file.name ~~ 'draft-*'"
        assert spec.frontmatter == "Course == 'X'"


class TestBoundedScan:
    def test_it_finds_kinds_and_tags(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("---\ntags: [alpha]\n---\n", encoding="utf-8")
        (tmp_path / "b.txt").write_text("x", encoding="utf-8")
        got = sample_source(tmp_path)
        assert got.kinds == {"md": 1, "txt": 1}
        assert got.tags.get("frontmatter", {}).get("alpha") == 1

    def test_it_records_frontmatter_keys(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("---\nCourse: DPwC\n---\n", encoding="utf-8")
        assert "Course" in sample_source(tmp_path).frontmatter_keys

    def test_the_file_budget_truncates_rather_than_running_on(self, tmp_path: Path) -> None:
        for i in range(30):
            (tmp_path / f"n{i}.md").write_text("x", encoding="utf-8")
        got = sample_source(tmp_path, max_files=5)
        assert got.files_seen == 5
        assert got.truncated is True

    def test_a_malformed_note_does_not_stop_the_scan(self, tmp_path: Path) -> None:
        (tmp_path / "bad.md").write_text("---\n  nope\n---\n", encoding="utf-8")
        (tmp_path / "good.md").write_text("---\ntags: [ok]\n---\n", encoding="utf-8")
        got = sample_source(tmp_path)
        assert got.files_seen == 2
        assert got.tags.get("frontmatter", {}).get("ok") == 1


class TestTagTriState:
    """The tag rows carry the query pane's ●/⊘/○, and all three must mean something."""

    def test_an_included_tag_round_trips(self) -> None:
        spec = FilterSpec(include_tags={"frontmatter": ("readings",)})
        selected, excluded = selection_for(spec, gitignore=True, fndignore=True)
        assert "tag:frontmatter:readings" in selected
        back, _g, _f = apply_selection(spec, selected, excluded)
        assert back.include_tags == {"frontmatter": ("readings",)}

    def test_include_and_exclude_are_separate_sets(self) -> None:
        spec = FilterSpec(include_tags={"os": ("keep",)}, exclude_tags={"frontmatter": ("drop",)})
        selected, excluded = selection_for(spec, gitignore=True, fndignore=True)
        assert "tag:os:keep" in selected
        assert excluded == {"tag:frontmatter:drop"}
        back, _g, _f = apply_selection(spec, selected, excluded)
        assert back == spec

    def test_a_configured_include_tag_appears_even_if_unscanned(self) -> None:
        spec = FilterSpec(include_tags={"os": ("never_scanned",)})
        tags = next(b for b in spec_branches(spec, _sample()) if b.id == "tags")
        os_group = next(g for g in tags.groups if g.id == "tags:os")
        assert any(i[0] == "tag:os:never_scanned" for i in os_group.items)


class TestEveryTypeTickedMeansEveryType:
    """The tree lists only the types a source contains, so ticking every box is
    the user saying "all of them". Freezing the sampled list meant a PDF added
    later was never indexed, while leaving the branch alone indexed it."""

    def test_ticking_every_offered_type_stores_no_restriction(self) -> None:
        offered = {"kind:md", "kind:python", "kind:txt"}
        spec, _g, _f = apply_selection(FilterSpec(), offered, set(), offered)
        assert spec.kinds == ()

    def test_ticking_some_still_restricts(self) -> None:
        offered = {"kind:md", "kind:python", "kind:txt"}
        spec, _g, _f = apply_selection(FilterSpec(), {"kind:md", "kind:txt"}, set(), offered)
        assert spec.kinds == ("md", "txt")

    def test_without_an_offered_set_every_registry_kind_collapses(self) -> None:
        from fnd.kinds import ALL_KIND_IDS

        every = {f"kind:{k}" for k in ALL_KIND_IDS}
        spec, _g, _f = apply_selection(FilterSpec(), every, set())
        assert spec.kinds == ()


class TestACustomBoundStaysOnOffer:
    """Its row exists only while the spec holds it, so picking a preset over a
    custom value discarded the value with no way back to it."""

    @staticmethod
    def _labels(spec: FilterSpec, branch: str, keep: dict[str, str]) -> list[str]:
        return [
            lbl for b in spec_branches(spec, None, keep) if b.id == branch for _i, lbl in b.items
        ]

    def test_the_row_survives_moving_off_it(self) -> None:
        held = FilterSpec(max_size=7_000_000)
        keep = custom_ids(held)
        moved = replace(held, max_size=1_000_000)
        assert "Under 7 MB" not in self._labels(moved, "size", {})
        assert "Under 7 MB" in self._labels(moved, "size", keep)

    def test_selecting_it_again_restores_the_exact_bound(self) -> None:
        moved = FilterSpec(max_size=1_000_000)
        selected, excluded = selection_for(moved)
        selected = {i for i in selected if not i.startswith("size:")} | {"size:custom:7000000"}
        spec, _g, _f = apply_selection(moved, selected, excluded)
        assert spec.max_size == 7_000_000

    def test_rows_stay_ordered_by_the_bound_they_set(self) -> None:
        keep = custom_ids(FilterSpec(max_size=7_000_000))
        labels = self._labels(FilterSpec(), "size", keep)
        assert labels.index("Under 7 MB") == labels.index("Under 1 MB") + 1
