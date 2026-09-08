"""Bringing a config file up to the current shape, once, on disk.

Each entry moves a config one version forward. A migration exists so a legacy
shape can be *retired* rather than honoured forever: once every config on disk
is at version N, the compatibility code for anything older can go.

Two kinds of step:

* A shape the models already normalise on load; a legacy key promoted by a
  validator; needs no transform here. Loading and re-rendering persists the
  normalised form, so the entry is a no-op with a note saying why.
* A shape the models cannot read at all, such as a key renamed out from under
  them, needs a real transform over the raw mapping, before validation.
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any, Final

#: What this build writes. Bump when adding a migration.
CONFIG_VERSION: Final = 2

VERSION_KEY: Final = "config_version"

Transform = Callable[[MutableMapping[str, Any]], None]


def _to_v1(raw: MutableMapping[str, Any]) -> None:
    """Retire ``frontmatter_filter`` into the source's filters table.

    Flat ``roots`` and complete sets of type globs in ``includes`` are promoted
    by model validators, so re-rendering persists them unaided. This one is not:
    the model keeps the legacy field as it found it, so without an explicit move
    the rule would be carried forever, or dropped.
    """
    collections = raw.get("collections")
    if not isinstance(collections, dict):
        return
    for collection in collections.values():
        if not isinstance(collection, dict):
            continue
        for source in collection.get("sources") or ():
            if not isinstance(source, dict):
                continue
            legacy = source.pop("frontmatter_filter", None)
            if not legacy:
                continue
            filters = source.setdefault("filters", {})
            if isinstance(filters, dict):
                filters.setdefault("frontmatter", legacy)


def _to_v2(raw: MutableMapping[str, Any]) -> None:
    """Anchor a slashless glob, which used to match at any depth.

    Globs were `fnmatch`, whose `*` crosses `/`, so `includes = ["*.md"]` took
    every `.md` in the tree. They are path globs now and `*` stops at a
    separator, which would silently narrow such a source to its root and let
    the next update prune everything below it out of the index. `**/` restores
    the reach the pattern had when it was written.
    """
    for collection in (raw.get("collections") or {}).values():
        if not isinstance(collection, dict):
            continue
        for source in collection.get("sources") or ():
            if not isinstance(source, dict):
                continue
            for key in ("includes", "excludes"):
                globs = source.get(key)
                if isinstance(globs, list):
                    source[key] = [
                        f"**/{g}" if isinstance(g, str) and "/" not in g else g for g in globs
                    ]


MIGRATIONS: Final[tuple[tuple[int, str, Transform], ...]] = (
    (1, "Adopt the canonical layout and record a config version", _to_v1),
    (2, "Anchor slashless globs so they still match at any depth", _to_v2),
)


class ConfigTooNewError(Exception):
    """A config written by a newer fnd. Loading it would silently drop keys."""

    def __init__(self, found: int, supported: int) -> None:
        super().__init__(
            f"config_version = {found}, but this fnd understands up to "
            f"{supported}. Update fnd, or restore the backup written beside "
            f"the config when it was last migrated."
        )
        self.found = found
        self.supported = supported

    def __reduce__(self) -> tuple[Any, tuple[int, int]]:
        return (ConfigTooNewError, (self.found, self.supported))


def version_of(raw: MutableMapping[str, Any]) -> int:
    """The version a raw config declares. Absent means pre-versioning."""
    value = raw.get(VERSION_KEY, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def check_version(raw: MutableMapping[str, Any]) -> int:
    """Refuse a config from a newer fnd, and consume the key so it never
    reaches a model that forbids unknown fields. Applies no transform."""
    found = version_of(raw)
    if found > CONFIG_VERSION:
        raise ConfigTooNewError(found, CONFIG_VERSION)
    raw.pop(VERSION_KEY, None)
    return found


def migrate(raw: MutableMapping[str, Any]) -> tuple[int, list[str]]:
    """Apply every outstanding step in place. Returns the version reached and
    what was done, so the caller can report it."""
    found = check_version(raw)
    applied: list[str] = []
    for target, description, transform in MIGRATIONS:
        if found < target:
            transform(raw)
            applied.append(description)
    return CONFIG_VERSION, applied
