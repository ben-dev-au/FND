"""60 equal-scoring sections of one file rendered "Day 3 … Day 60, Day 1, Day 2".

Equal scores come back in whatever order the segments hold, and the list the
user reads showed them that way. The match navigator already sorted them by
`chunk_seq` before using them, which is the tell: the order was known to be
wrong by the one consumer that depended on it.
"""

from __future__ import annotations

from fnd.query import Hit, group_by_file


def _hit(seq: int, *, score: float = 1.0, line: int = 0, heading: str = "") -> Hit:
    return Hit(
        score=score,
        parent_id="file-1",
        path="/notes/journal.md",
        kind="md",
        page=0,
        slide=0,
        heading_path=heading or f"Day {seq}",
        title="journal",
        snippet="",
        chunk_seq=seq,
        line=line,
    )


def test_equal_scores_read_in_sequence() -> None:
    scrambled = [_hit(3), _hit(60), _hit(1), _hit(2)]

    groups = group_by_file(scrambled, limit=10, sections_per_file=10)

    assert [h.chunk_seq for h in groups[0].hits] == [1, 2, 3, 60]


def test_the_group_still_ranks_on_its_best_section() -> None:
    """The control: ordering the sections must not restate the file's score."""
    hits = [_hit(9, score=5.0), _hit(1, score=0.5)]

    groups = group_by_file(hits, limit=10, sections_per_file=10)

    assert groups[0].top_score == 5.0, "the group ranks on the best hit, not the first one"
    assert [h.chunk_seq for h in groups[0].hits] == [1, 9]


def test_selection_is_still_by_score() -> None:
    """The cap keeps the best sections; only their order changes."""
    hits = [_hit(9, score=5.0), _hit(5, score=4.0), _hit(1, score=0.1)]

    groups = group_by_file(hits, limit=10, sections_per_file=2)

    assert [h.chunk_seq for h in groups[0].hits] == [5, 9], (
        "the weak one is dropped, not reordered in"
    )


def test_files_keep_their_ranked_order() -> None:
    """Between files nothing changes: the caller's ranking is the order."""
    hits = [
        _hit(7, score=9.0),
        Hit(
            score=8.0,
            parent_id="file-2",
            path="/notes/other.md",
            kind="md",
            page=0,
            slide=0,
            heading_path="A",
            title="other",
            snippet="",
            chunk_seq=1,
        ),
    ]

    groups = group_by_file(hits, limit=10, sections_per_file=10)

    assert [g.parent_id for g in groups] == ["file-1", "file-2"]


def test_a_kind_without_sequence_numbers_is_untouched() -> None:
    """PDF-shaped hits carry `chunk_seq` 0; a stable sort must not shuffle."""
    hits = [_hit(0, heading=f"page {n}") for n in range(3)]

    groups = group_by_file(hits, limit=10, sections_per_file=10)

    assert [h.heading_path for h in groups[0].hits] == ["page 0", "page 1", "page 2"]
