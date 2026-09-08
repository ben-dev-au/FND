"""Every "unknown field" error reported column 1, whatever the column was.

It is the one error kind the live editor could not point at: a hunter checked
six expressions and found every other kind reporting its true column, one of
them 41, while this one always said 1. `referenced_fields` returns names and
not positions, and I raised with a literal.
"""

from __future__ import annotations

import pytest

from fnd.filters.text_form import parse_or_error


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("file.totally_bogus == 1", "file.totally_bogus"),
        ("file.kind == 'md' AND file.kinds == 'pdf'", "file.kinds"),
        ("NOT (file.size <= 10) AND file.nope == 2", "file.nope"),
    ],
)
def test_the_column_lands_on_the_field(text: str, field: str) -> None:
    _spec, err = parse_or_error(text)

    assert err is not None
    assert text[err.column - 1 :].startswith(field), (err.column, text)


def test_the_message_still_names_it_and_the_known_ones() -> None:
    _spec, err = parse_or_error("file.kinds == 'pdf'")

    assert err is not None
    assert "file.kinds" in err.message
    assert "file.kind" in err.message, "the near-miss it is one letter from"


def test_a_valid_expression_is_untouched() -> None:
    """The control."""
    spec, err = parse_or_error("file.kind in ['md']")

    assert err is None
    assert spec is not None
