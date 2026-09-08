"""A frontmatter rule judges a note that has no block, and drops it.

Skipping such a file turned "index this course" into "index everything except
other courses": every untagged note in a vault reached the index, and the
search that found them named a course filter it had never applied.

The rule still must not judge a PDF, which cannot answer the question — and it
must judge any file that does carry a block, whatever its extension.
"""

from __future__ import annotations

from pathlib import Path

from fnd.file_facts import FileFacts
from fnd.filters.dimensions import dimension
from fnd.walk import walk_sources

_RULE = "Course == 'Unstructured Data' AND NOT ('private' in tags)"


def _facts(path: Path, root: Path) -> FileFacts:
    return FileFacts(path, root=root)


def test_a_note_with_no_block_is_dropped(tmp_path: Path) -> None:
    (tmp_path / "bare.md").write_text("# Daily note\n\nnothing declared\n", encoding="utf-8")
    rule = dimension("frontmatter").rule(_RULE)

    assert rule is not None
    assert not rule.passes(_facts(tmp_path / "bare.md", tmp_path))


def test_a_note_that_answers_the_rule_is_kept(tmp_path: Path) -> None:
    (tmp_path / "wk2.md").write_text(
        "---\nCourse: Unstructured Data\ntags: []\n---\n\nnotes\n", encoding="utf-8"
    )
    (tmp_path / "other.md").write_text(
        "---\nCourse: Software Design\ntags: []\n---\n\nnotes\n", encoding="utf-8"
    )
    rule = dimension("frontmatter").rule(_RULE)

    assert rule is not None
    assert rule.passes(_facts(tmp_path / "wk2.md", tmp_path))
    assert not rule.passes(_facts(tmp_path / "other.md", tmp_path))


def test_a_pdf_is_still_not_judged(tmp_path: Path) -> None:
    """The control the skip existed for: strict null on a file that cannot
    carry frontmatter would drop every PDF in the source."""
    (tmp_path / "lecture.pdf").write_bytes(b"%PDF-1.4\n")
    rule = dimension("frontmatter").rule(_RULE)

    assert rule is not None
    assert rule.passes(_facts(tmp_path / "lecture.pdf", tmp_path))


def test_the_walk_leaves_the_untagged_note_out(tmp_path: Path) -> None:
    """End to end through the walk, which is where the index gets its files."""
    from fnd.config import SourceConfig

    root = tmp_path / "vault"
    root.mkdir()
    (root / "bare.md").write_text("# Daily\n\nno block\n", encoding="utf-8")
    (root / "wk2.md").write_text(
        "---\nCourse: Unstructured Data\ntags: []\n---\n\nnotes\n", encoding="utf-8"
    )
    (root / "lecture.pdf").write_bytes(b"%PDF-1.4\n")
    source = SourceConfig.model_validate({"path": str(root), "filters": {"frontmatter": _RULE}})

    found = {p.name for p in walk_sources(sources=[source])}

    assert "wk2.md" in found, found
    assert "lecture.pdf" in found, "a PDF cannot answer the rule and must not be judged"
    assert "bare.md" not in found, "an untagged note reached the index anyway"
