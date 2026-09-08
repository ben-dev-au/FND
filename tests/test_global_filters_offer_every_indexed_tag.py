"""The defaults screen offers every tag in the index, not the first few it walked.

`_distinct_roots` capped the scan at the first three collections and their
first two sources, so on a twelve-collection config the screen sampled five
roots, flagged itself "partial scan", and simply did not offer the tags of the
other nine. These are the defaults for EVERY collection, so the answer wanted
is every collection's tags.

The index already holds them. Asking it is faster than the capped walk was,
opens no file, and hydrates nothing from a cloud folder — measured at 65 ms
for 141 distinct tags across a real twelve-collection index.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from fnd.config import Config, load
from fnd.index import build_index_from_config
from fnd.tui import FNDApp
from fnd.tui.menu import _sample_first_source


@pytest.fixture
def three_collections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Config, Path]:
    """More collections than the old walk would reach, each with its own tag."""
    index_dir = tmp_path / "index"
    lines = []
    for n in range(4):
        root = tmp_path / f"c{n}"
        root.mkdir()
        (root / "note.md").write_text(f"---\ntags: [only_in_c{n}]\n---\n\nbody\n", encoding="utf-8")
        lines.append(f'[[collections.c{n}.sources]]\npath = "{root}"\n')
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(textwrap.dedent("".join(lines)), encoding="utf-8")
    monkeypatch.setattr("fnd.config.default_config_path", lambda: cfg_path)
    cfg = load(cfg_path)
    for name, collection in cfg.collections.items():
        build_index_from_config(config=collection, collection=name, index_dir=index_dir)
    return cfg, index_dir


@pytest.mark.asyncio
async def test_a_tag_from_the_last_collection_is_offered(
    three_collections: tuple[Config, Path],
) -> None:
    cfg, index_dir = three_collections
    app = FNDApp(index_dir=index_dir, config=cfg)
    async with app.run_test(size=(110, 30)) as pilot:
        for _ in range(15):
            await pilot.pause()
        sample = _sample_first_source(app)

    assert sample is not None
    offered = set(sample.tags.get("frontmatter", {}))
    assert offered == {f"only_in_c{n}" for n in range(4)}, offered


@pytest.mark.asyncio
async def test_it_does_not_call_itself_partial(
    three_collections: tuple[Config, Path],
) -> None:
    """The walk flagged `truncated` because it genuinely was. The index is
    the whole answer, so claiming partial would be its own dishonesty."""
    cfg, index_dir = three_collections
    app = FNDApp(index_dir=index_dir, config=cfg)
    async with app.run_test(size=(110, 30)) as pilot:
        for _ in range(15):
            await pilot.pause()
        sample = _sample_first_source(app)

    assert sample is not None
    assert not sample.truncated, "it called a complete answer partial"


@pytest.mark.asyncio
async def test_an_unbuilt_corpus_still_gets_suggestions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_index_dir: Path
) -> None:
    """The control: a corpus that has never been indexed has no indexed tags,
    and a first-run user still needs the picker to offer something. The walk
    stays as the fallback, not as a second mechanism."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.md").write_text("---\ntags: [never_indexed]\n---\n\nbody\n", encoding="utf-8")
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(f"""
            [[collections.fresh.sources]]
            path = "{root}"
        """),
        encoding="utf-8",
    )
    monkeypatch.setattr("fnd.config.default_config_path", lambda: cfg_path)
    cfg = load(cfg_path)

    app = FNDApp(index_dir=tmp_index_dir, config=cfg)
    async with app.run_test(size=(110, 30)) as pilot:
        for _ in range(15):
            await pilot.pause()
        sample = _sample_first_source(app)

    assert sample is not None
    assert "never_indexed" in sample.tags.get("frontmatter", {}), sample.tags


def test_the_index_lookup_survives_a_stub_app() -> None:
    """The settings invariant tests drive these getters with a SimpleNamespace
    carrying only `_config`. Reaching straight through `app._search` raised
    AttributeError and took the walk fallback down with it — eight tests, all
    of them about the fallback rather than about the index."""
    from types import SimpleNamespace
    from typing import Any, cast

    from fnd.tui.menu import _indexed_tags

    stub = SimpleNamespace(_config=None)
    assert _indexed_tags(cast("Any", stub)) is None
