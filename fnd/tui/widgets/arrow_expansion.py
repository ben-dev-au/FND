"""Key behaviour shared by every tree fnd defines."""

from __future__ import annotations

from typing import Any

__all__ = ["ArrowsExpand", "HomeToFirstRow"]


class ArrowsExpand:
    """Mixin for a ``Tree``: Textual's stock ``space`` → ``toggle_node`` is off.

    Space was a second expand key that disagreed with the first — on a
    ``ToggleTree`` row it toggled the selection instead, so one key did two
    different things in two panes of the same screen.
    """

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "toggle_node":
            return None
        return super().check_action(action, parameters)  # type: ignore[misc]


#: How far down to look for a row the cursor may rest on. A header run longer
#: than this is not a tree anyone is navigating with Home.
_FIRST_ROW_SCAN = 64


class HomeToFirstRow:
    """Mixin for a ``Tree``: ``home`` moves the cursor to the first row.

    ``end`` already reached the last one and ``home`` did nothing at all — the
    scroll view's own binding scrolls a viewport that the cursor then does not
    follow, so the pane looked frozen.
    """

    def action_cursor_first(self) -> None:
        tree: Any = self
        if not tree.root.children:
            return
        # The tree's own `validate_cursor_line` decides what is selectable —
        # the results tree refuses an expanded parent, and refuses it BY
        # DIRECTION, so an upward move onto line 0 is a no-op. Walking down
        # until it accepts one keeps that rule in the one place that owns it.
        for line in range(min(_FIRST_ROW_SCAN, len(tree._tree_lines))):
            tree.cursor_line = line
            if tree.cursor_line == line:
                break
        # To the top of the list, not to the cursor: the first row may be an
        # expanded parent the cursor cannot rest on, and leaving it just off
        # screen is not "Home".
        tree.scroll_to_line(0, animate=False)
