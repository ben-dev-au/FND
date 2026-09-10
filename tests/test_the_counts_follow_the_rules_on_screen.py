"""The sample was scanned once at mount and never again.

So every number beside a file type described the rules the screen OPENED with.
A typed rule selecting nothing left `Markdown · 6, Plain text · 5` on a screen
whose own expression matched zero, and the save that followed removed eleven
documents. The pane was the only thing that disagreed with the config, the
walk and the indexer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from fnd.filters import FilterSpec
from fnd.filters.scan import SourceSample
from fnd.index import build_index
from fnd.tui import FNDApp
from fnd.tui.settings_screen import FilterBrowserScreen
from tests._pilot_wait import wait_until


@pytest.fixture
def built_index(tmp_path: Path, tmp_index_dir: Path) -> Path:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.md").write_text("# A\n\nrisotto.\n", encoding="utf-8")
    build_index(roots=[root], index_dir=tmp_index_dir, collection="c")
    return tmp_index_dir


def _provider(seen: list[Any]) -> Any:
    """A stand-in for the walk: it answers from the spec it is handed, so the
    test measures whether the screen re-asks, not how the walk counts."""

    def sample(spec: Any = None) -> SourceSample:
        seen.append(spec)
        if spec is not None and getattr(spec, "expression", ""):
            return SourceSample(kinds={"md": 6}, kinds_kept={}, gated=True)
        return SourceSample(kinds={"md": 6}, kinds_kept={"md": 6}, gated=True)

    return sample


async def _open(app: FNDApp, pilot: Any, seen: list[Any]) -> FilterBrowserScreen:
    screen = FilterBrowserScreen(
        title="Index filters",
        spec=FilterSpec(kinds=("md",)),
        gitignore=True,
        fndignore=True,
        sample_provider=_provider(seen),
        on_save=lambda *_a: None,
    )
    app.push_screen(screen)
    await wait_until(
        pilot,
        lambda: app.screen is screen and bool(screen.query("#filter_tree")),
        timeout=20.0,
        message="the browser never composed",
    )
    await wait_until(
        pilot,
        lambda: screen._sample is not None,
        timeout=20.0,
        message="the first scan never landed",
    )
    return screen


@pytest.mark.asyncio
async def test_a_new_rule_makes_the_counts_be_recomputed(built_index: Path) -> None:
    app = FNDApp(index_dir=built_index)
    seen: list[Any] = []
    async with app.run_test(size=(110, 34)) as pilot:
        screen = await _open(app, pilot, seen)
        first = len(seen)
        assert first >= 1, "the mount scan is the baseline"

        # What `t` does when a typed rule is applied.
        screen._spec = FilterSpec(kinds=("md",), expression="file.path == 'x'")
        screen._rebuild(focus_tree=False)
        await wait_until(
            pilot,
            lambda: len(seen) > first,
            timeout=20.0,
            message="the counts were never recomputed for the new rule",
        )
        await wait_until(
            pilot,
            lambda: screen._sampled_spec == screen._spec,
            timeout=20.0,
            message="the sample never caught up with the spec",
        )
        kept = dict(screen._sample.kinds_kept)

    assert getattr(seen[-1], "expression", "") == "file.path == 'x'", seen[-1]
    assert kept == {}, "the rule selects nothing, and the counts must say so"


@pytest.mark.asyncio
async def test_an_unchanged_spec_is_not_rescanned(built_index: Path) -> None:
    """The control. A rebuild happens on every keystroke in the row filter, and
    each scan walks the source."""
    app = FNDApp(index_dir=built_index)
    seen: list[Any] = []
    async with app.run_test(size=(110, 34)) as pilot:
        screen = await _open(app, pilot, seen)
        first = len(seen)

        for _ in range(3):
            screen._rebuild(focus_tree=False)
            await pilot.pause()
        # Real time, not ticks: the debounce is a 0.3s timer, so a scan it had
        # scheduled would have run by now.
        await asyncio.sleep(0.8)
        await pilot.pause()

    assert len(seen) == first, f"{len(seen) - first} needless scans"
