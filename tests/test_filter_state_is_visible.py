"""A filter row's state carries colour as well as shape, and no_index cannot
be inverted.

`●`, `⊘` and `○` were painted the same colour and weight: `⊘` and `○` differ
by a hairline and mean opposites. Colour is a second channel beside the glyph,
not instead of it, and it is spent on the two states that change what gets
indexed.

`no_index` ships excluded, so one press on the state a user finds turned "never
index these" into "index ONLY these" — nine files to zero, a reindex to undo.
It skips include entirely; every other tag keeps the full cycle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fnd.filters import FilterSpec
from fnd.filters.scan import SourceSample
from fnd.tui import FNDApp
from fnd.tui.settings_screen import FilterBrowserScreen
from fnd.tui.widgets.toggle_tree import ToggleTree


@pytest.fixture
def cfg_and_index(tmp_path: Path, tmp_index_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """A real index with tags, so the sidebar has rows to paint."""
    import textwrap

    from fnd.config import load
    from fnd.index import build_index

    root = tmp_path / "papers"
    root.mkdir()
    (root / "a.md").write_text("---\ntags: [recipe, dinner]\n---\n\nsaffron\n", encoding="utf-8")
    build_index(roots=[root], index_dir=tmp_index_dir, collection="papers")
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(f"""
            [[collections.papers.sources]]
            path = "{root}"
        """),
        encoding="utf-8",
    )
    monkeypatch.setattr("fnd.config.default_config_path", lambda: cfg_path)
    return load(cfg_path), tmp_index_dir


_SAMPLE = SourceSample(kinds={"md": 3, "pdf": 1}, tags={"frontmatter": {"no_index": 1, "keep": 2}})


async def _tree(app: FNDApp, pilot: object, spec: FilterSpec) -> ToggleTree:
    app.push_screen(
        FilterBrowserScreen(
            title="Index filters",
            spec=spec,
            gitignore=True,
            fndignore=True,
            sample_provider=lambda: _SAMPLE,
            on_save=lambda *_a: None,
        )
    )
    for _ in range(25):
        await pilot.pause()  # type: ignore[attr-defined]
    tree = app.screen.query_one("#filter_tree", ToggleTree)
    # Only the branches under test: File types now offers all forty kinds, so
    # expanding everything pushes the tag rows off the screen.
    for node in tree.root.children:
        if any(word in str(node.label) for word in ("tags", "Notes & text")):
            node.expand()
            for child in node.children:
                child.expand()
    for _ in range(8):
        await pilot.pause()  # type: ignore[attr-defined]
    return tree


def _marker_colours(app: FNDApp) -> dict[str, set[str]]:
    """Every colour each glyph is painted in, not the first.

    The legend row spells the glyphs out unstyled, so taking the first
    occurrence measured the legend and never reached a row.
    """
    out: dict[str, set[str]] = {"●": set(), "⊘": set(), "○": set()}
    for strip in app.screen._compositor.render_strips():
        for seg in strip:
            glyph = seg.text.strip()
            if glyph in out and seg.style and seg.style.color:
                out[glyph].add(str(seg.style.color))
    return out


@pytest.mark.asyncio
async def test_include_and_exclude_carry_different_colours(tmp_index_dir: Path) -> None:
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        # Both states in the one branch the helper expands: an included tag
        # beside an excluded one.
        await _tree(
            app,
            pilot,
            FilterSpec(
                include_tags={"frontmatter": ("keep",)},
                exclude_tags={"frontmatter": ("no_index",)},
            ),
        )
        painted = _marker_colours(app)
        success = app.get_css_variables().get("success", "")
        error = app.get_css_variables().get("error", "")

    assert any(success.lower() in c.lower() for c in painted["●"]), painted
    assert any(error.lower() in c.lower() for c in painted["⊘"]), painted


@pytest.mark.asyncio
async def test_the_off_state_carries_none(tmp_index_dir: Path) -> None:
    """The control: colour marks the states that change the index, so the
    neutral one must not compete with them."""
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await _tree(app, pilot, FilterSpec(kinds=("md",)))
        painted = _marker_colours(app)

    assert painted["○"] == set(), painted


@pytest.mark.asyncio
async def test_no_index_cycles_past_include(tmp_index_dir: Path) -> None:
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        tree = await _tree(app, pilot, FilterSpec(exclude_tags={"frontmatter": ("no_index",)}))
        item = "tag:frontmatter:no_index"
        assert item in tree._excluded, "the premise: it ships excluded"
        tree._cycle(item)
        after_one = (item in tree._excluded, item in tree._selected)
        tree._cycle(item)
        after_two = (item in tree._excluded, item in tree._selected)

    assert after_one == (False, False), "one press must reach off, not include"
    assert after_two == (True, False), "and the next returns to never-index"


@pytest.mark.asyncio
async def test_every_other_tag_keeps_the_full_cycle(tmp_index_dir: Path) -> None:
    """The control: the exception is one tag, not a change to the mechanism."""
    app = FNDApp(index_dir=tmp_index_dir)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        tree = await _tree(app, pilot, FilterSpec(exclude_tags={"frontmatter": ("keep",)}))
        item = "tag:frontmatter:keep"
        assert item in tree._excluded, "the premise"
        tree._cycle(item)
        reached_include = item in tree._selected

    assert reached_include, "an ordinary tag must still reach index-only"


@pytest.mark.asyncio
async def test_the_sidebar_paints_the_same_states_the_same_way(
    cfg_and_index: tuple[object, Path],
) -> None:
    """The two panes are both called Filters. The sidebar hand-rolls its
    markers rather than using ToggleTree, so the same state read differently
    in each until they shared one mapping."""
    config, index_dir = cfg_and_index
    app = FNDApp(index_dir=index_dir, config=config)  # type: ignore[arg-type]
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._scope.tag_include["frontmatter"] = {"recipe"}
        app._scope.tag_exclude["frontmatter"] = {"dinner"}
        app._scope.refresh_filters_panel()
        for _ in range(8):
            await pilot.pause()
        from textual.widgets import Tree

        tree = app.query_one("#filters_panel_tree", Tree)
        for node in tree.root.children:
            node.expand()
            for child in node.children:
                child.expand()
        for _ in range(8):
            await pilot.pause()
        painted = _marker_colours(app)
        success = app.get_css_variables().get("success", "")
        error = app.get_css_variables().get("error", "")
        # Prove the sidebar is what was measured: without this the assertions
        # below pass on any coloured marker anywhere on the screen.
        on_screen = "\n".join(
            "".join(s.text for s in strip) for strip in app.screen._compositor.render_strips()
        )

    assert "recipe" in on_screen, "the sidebar rows never reached the screen"
    assert any(success.lower() in c.lower() for c in painted["●"]), painted
    assert any(error.lower() in c.lower() for c in painted["⊘"]), painted
