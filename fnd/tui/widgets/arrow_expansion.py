"""One expand/collapse key per tree, and it is the arrows."""

from __future__ import annotations

__all__ = ["ArrowsExpand"]


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
