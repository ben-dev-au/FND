"""The save gesture is written one way, everywhere.

It was `Ctrl+S` in three places and `^S` in four, on screens a user moves
between in one session — `app._is_commit` normalises both spellings, so the
code already knew. Lowercase, because it sits beside `t`, `c` and `y` hints
and a capital reads as though Shift is wanted.
"""

from __future__ import annotations

import re
from pathlib import Path

from fnd.tui.widgets import COMMIT_KEY

_TUI = Path(__file__).resolve().parent.parent / "fnd" / "tui"


def test_no_module_spells_it_another_way() -> None:
    offenders: list[str] = []
    for path in sorted(_TUI.rglob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "Binding(" in line:
                continue  # the key itself, not the label shown for it
            if re.search(r'"(Ctrl\+S|\^S)"', line):
                offenders.append(f"{path.name}:{n}")
    assert not offenders, f"the save key spelled another way: {offenders}"


def test_it_carries_no_capital() -> None:
    assert COMMIT_KEY == COMMIT_KEY.lower(), COMMIT_KEY


def test_the_app_still_recognises_both_spellings() -> None:
    """The control: the footer's fitting code drops anchors before a screen's
    own keys, and it finds the save hint by name."""
    from fnd.tui.app import _is_commit

    assert _is_commit(COMMIT_KEY)
    assert _is_commit("Ctrl+S"), "an older spelling must still be recognised"
