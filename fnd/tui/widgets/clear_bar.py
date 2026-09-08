"""Focusable clear-filters bar docked at the top of a filters pane.

A plain Static can't be reached by the keyboard, so the bar is its own
focusable widget: Up from the top of the filters tree focuses it, Enter clears,
and Down returns to the tree. It stays clickable, and the pane's clear key
still clears from anywhere.

Both filter panes mount one. A key advertised in a footer is not an
affordance — the settings pane cleared on `c` and showed nothing that said so,
while the sidebar had a row you could see, focus and click.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from textual import events
from textual.widget import Widget
from textual.widgets import Static

#: Both panes mount their bar under this id; a screen holds at most one.
CLEAR_BAR_ID = "clear_filters_bar"


def clear_label(n: int) -> str:
    """What the bar says over the SEARCH filters: ``n`` of them, cleared.

    Search filters are ephemeral and clearing them costs nothing, so the row
    counts what it will remove.
    """
    return f"✕  Clear {n} filter{'' if n == 1 else 's'}"


#: What the same bar says over the INDEX filters. A different act, so a
#: different word: these are config, they decide what is in the index, and the
#: row restores what the source inherits rather than removing anything.
RETURN_TO_DEFAULTS = "✕  Return to default filters"


def focus_clear_bar(tree: Widget) -> bool:
    """Focus the clear bar above ``tree``, if its pane is showing one.

    Scoped to the tree's own screen: the sidebar and the settings pane both
    mount a bar, and an app-wide lookup would find whichever came first.
    """
    with contextlib.suppress(Exception):
        bar = tree.screen.query_one(f"#{CLEAR_BAR_ID}", ClearFiltersBar)
        if bar.visible:
            bar.focus()
            return True
    return False


class ClearFiltersBar(Static):
    can_focus = True

    def __init__(
        self,
        renderable: str = "",
        *,
        id: str | None = None,
        on_clear: Callable[[], None] | None = None,
        focus_id: str = "filters_panel_tree",
    ) -> None:
        super().__init__(renderable, id=id)
        self._on_clear = on_clear
        self._focus_id = focus_id

    def on_click(self, event: events.Click) -> None:
        """The widget's own click, not the app's.

        An app-level handler on this id caught BOTH panes' bars once the
        settings pane mounted one: clicking the row that names the index
        filters wiped the live search filters instead.
        """
        event.stop()
        self._clear()

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            self._clear()
            # Clearing hid the bar; move focus back to the tree.
            self._focus_tree()
        elif event.key in ("down", "up"):
            event.stop()
            self._focus_tree()

    def _clear(self) -> None:
        if self._on_clear is not None:
            self._on_clear()
            return
        self.app._scope.clear_filters()  # type: ignore[attr-defined]

    def _focus_tree(self) -> None:
        with contextlib.suppress(Exception):
            self.app.query_one(f"#{self._focus_id}").focus()
