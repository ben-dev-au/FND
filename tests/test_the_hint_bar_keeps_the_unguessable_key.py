"""At 62 columns the footer elided `Tab  Completed` and kept `↑↓ Choose`,
`⏎ Select` and `Esc Close`.

Those three are what a user tries unprompted. `Tab` was the only non-obvious
one, and the only route into the run history: the feature was advertised at
wide widths and unreachable in practice at the persona's.
"""

from __future__ import annotations

from fnd.tui.app import render_hint_bar

_HINTS = (("↑↓", "Choose"), ("⏎", "Select"), ("Tab", "Completed"), ("Esc", "Close"))


def test_an_app_specific_key_outlives_a_guessable_one() -> None:
    """The hint worth its cells is the one nobody would guess."""
    narrow = render_hint_bar((), _HINTS).fitted(44).plain

    assert "Tab" in narrow, narrow
    assert "Choose" not in narrow, narrow


def test_the_way_out_is_never_dropped() -> None:
    """The existing rule still holds: leaving beats everything."""
    tiny = render_hint_bar((), _HINTS).fitted(20).plain

    assert "Esc" in tiny, tiny


def test_a_wide_bar_keeps_bar_order() -> None:
    """The control: ranking decides what is KEPT, never what order it reads
    in, so keys do not reshuffle as the pane resizes."""
    wide = render_hint_bar((), _HINTS).fitted(200).plain

    assert wide.index("Choose") < wide.index("Select") < wide.index("Completed"), wide
