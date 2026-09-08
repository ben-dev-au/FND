"""TUI widgets shared across settings screens."""

from fnd.tui.widgets.detail_strip import DetailStrip

#: How the save gesture is written in every footer and help table. Lowercase
#: beside the other single-key hints, where a capital reads as though Shift is
#: wanted; one name because it was spelled two ways on adjacent screens. Here
#: rather than in the app module, which menu.py cannot import at runtime.
COMMIT_KEY = "^s"

__all__ = ["COMMIT_KEY", "DetailStrip"]
