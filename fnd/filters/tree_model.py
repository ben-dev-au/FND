"""The filter set as the branches a tree shows, and back again.

Pure model: no Textual import, so the mapping between a
:class:`~fnd.filters.model.FilterSpec` and what the user sees is testable on
its own. The screen renders these groups and hands the selection back.

Date and size branches offer named windows rather than a typed value, and a
window resolves to an absolute bound when it is chosen — an index must not
change what it holds as the clock moves.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, replace

from fnd.filters.model import FilterSpec
from fnd.filters.scan import SourceSample
from fnd.kinds import ALL_KIND_IDS, CATEGORIES, KIND_BY_ID, KINDS_IN_CATEGORY

# Source-neutral labels: there are no Finder tags off macOS, and the branch
# should not name an OS the user is not on.
TAG_SOURCE_LABELS: dict[str, str] = {
    "os": "System tags",
    "frontmatter": "Note tags (YAML)",
}

__all__ = [
    "BRANCHES",
    "LEGEND",
    "apply_selection",
    "custom_ids",
    "selection_for",
    "spec_branches",
]

# (id, label, days back). ``None`` days = no bound.
_WINDOWS: tuple[tuple[str, str, int | None], ...] = (
    ("any", "Any time", None),
    ("7", "Last 7 days", 7),
    ("30", "Last 30 days", 30),
    ("90", "Last 3 months", 90),
    ("365", "Last 12 months", 365),
)

_SIZES: tuple[tuple[str, str, int | None], ...] = (
    ("any", "Any size", None),
    ("1mb", "Up to 1 MB", 1_000_000),
    ("10mb", "Up to 10 MB", 10_000_000),
    ("50mb", "Up to 50 MB", 50_000_000),
    ("200mb", "Up to 200 MB", 200_000_000),
)

BRANCHES = ("kinds", "tags", "ignore", "size", "modified", "created")

# Shown above the tree. The glyphs carry different polarity per branch —
# ● on a file type includes, ⊘ on a tag excludes — so the meaning is stated
# once here rather than guessed from each row.
LEGEND = "⊘  never index these   ●  index ONLY these   ◐  some of these   ○  no rule"


@dataclass(frozen=True, slots=True)
class Branch:
    """One collapsible row: its leaves, its sub-branches and how they behave.

    ``empty_label`` says what the branch means with nothing switched on —
    without it, "no file type ticked" reads as *nothing is indexed*.
    """

    id: str
    label: str
    mode: str
    items: tuple[tuple[str, str], ...] = ()  # (item id, label)
    groups: tuple[Branch, ...] = ()
    empty_label: str = ""
    noun: str = ""


def _kind_items(
    sample: SourceSample | None, configured: tuple[str, ...] = ()
) -> list[tuple[str, str, str]]:
    """(category id, kind id, label) for kinds present, or all when unknown.

    A kind the filter already names is offered even when the sample saw none:
    dropping the row leaves a rule the user can neither see nor switch off,
    under a branch that reads as unfiltered.
    """
    present = set(sample.kinds) if sample and sample.kinds else None
    if present is not None:
        present |= set(configured)
    out: list[tuple[str, str, str]] = []
    for cat in CATEGORIES:
        for kind in KINDS_IN_CATEGORY.get(cat.id, ()):
            if present is not None and kind not in present:
                continue
            spec = KIND_BY_ID.get(kind)
            if spec is None:
                continue
            count = (sample.kinds.get(kind, 0) if sample else 0) or 0
            suffixes = "/".join(spec.suffixes)
            label = f"{spec.label} ({suffixes})"
            out.append((cat.id, f"kind:{kind}", f"{label}  ·  {count}" if count else label))
    return out


def _beyond_the_pickers(spec: FilterSpec) -> tuple[tuple[str, str], ...]:
    """Bounds no branch can show, as (field, one-line description)."""
    out: list[tuple[str, str]] = []
    if spec.min_size is not None:
        out.append(("min_size", f"At least {_human_size(spec.min_size)}"))
    for field, verb in (("modified", "Modified"), ("created", "Created")):
        bound = getattr(spec, f"{field}_before")
        if bound is not None:
            out.append((f"{field}_before", f"{verb} before {bound.isoformat()}"))
    return tuple(out)


def _rule_label(name: str, value: str) -> str:
    """A typed rule's row: its current text, or that it has none."""
    text = (value or "").strip()
    return f"{name}   {text}" if text else f"{name}   (none)"


def _tag_branch(spec: FilterSpec, sample: SourceSample | None) -> Branch | None:
    """Tags, one sub-branch per source.

    A Finder tag and a note's ``tags:`` entry that share a word are different
    statements about a file, so they get different rows — the shape
    :class:`~fnd.tag_query.TagFilter` already uses on the query side.
    """
    sources = [s for s in TAG_SOURCE_LABELS if s in (sample.tags if sample else {})]
    for source in (*spec.include_tags, *spec.exclude_tags):
        if source not in sources and source in TAG_SOURCE_LABELS:
            sources.append(source)
    groups: list[Branch] = []
    for source in sources:
        seen = [
            (f"tag:{source}:{v}", f"{v}  ({c})")
            for v, c in (sample.tags_for(source) if sample else [])
        ]
        configured = set(spec.tag_includes.get(source, ())) | set(spec.tag_excludes.get(source, ()))
        for tag in sorted(configured):
            if not any(i[0] == f"tag:{source}:{tag}" for i in seen):
                seen.append((f"tag:{source}:{tag}", tag))
        # Whatever is switched on sorts first, so the branch shows what it is
        # doing without the user scrolling a corpus-length list to find it.
        active = {f"tag:{source}:{t}" for t in configured}
        items = [i for i in seen if i[0] in active] + [i for i in seen if i[0] not in active]
        if items:
            groups.append(
                Branch(f"tags:{source}", TAG_SOURCE_LABELS[source], "cycle", tuple(items))
            )
    if not groups:
        return None
    if len(groups) == 1:
        return replace(groups[0], id="tags", empty_label="any tag")
    return Branch("tags", "Tags", "cycle", groups=tuple(groups), empty_label="any tag", noun="tags")


def spec_branches(
    spec: FilterSpec,
    sample: SourceSample | None = None,
    keep_custom: Mapping[str, str] | None = None,
) -> list[Branch]:
    """The branches a filter screen should render for ``spec``.

    ``keep_custom`` names custom bounds to keep offering per branch even when
    the spec no longer holds them, so picking a preset over a custom value is
    reversible without retyping it in the text view.
    """
    branches: list[Branch] = []

    kinds = _kind_items(sample, spec.kinds)
    by_cat: dict[str, list[tuple[str, str]]] = {}
    for cat_id, kind, label in kinds:
        by_cat.setdefault(cat_id, []).append((kind, label))
    categories = tuple(
        Branch(f"kinds:{cat.id}", cat.label, "multi", tuple(by_cat[cat.id]))
        for cat in CATEGORIES
        if by_cat.get(cat.id)
    )
    if categories:
        branches.append(
            Branch(
                "kinds",
                "File types",
                "multi",
                groups=categories,
                empty_label="every type",
                noun="types",
            )
        )

    tag_branch = _tag_branch(spec, sample)
    if tag_branch is not None:
        branches.append(tag_branch)

    branches.append(
        Branch(
            "ignore",
            "Obey ignore files",
            "multi",
            (("ignore:git", ".gitignore"), ("ignore:fnd", ".fndignore")),
            empty_label="none",
            noun="files",
        )
    )
    # Rows stay ordered by the bound they set, so a custom one lands among the
    # presets rather than ahead of them.
    sized = [(-1 if v is None else v, f"size:{i}", lbl) for i, lbl, v in _SIZES]
    for custom in _custom_offers("size", spec, keep_custom):
        value = int(custom.removeprefix(f"{CUSTOM}:"))
        sized.append((value, f"size:{custom}", f"Up to {_human_size(value)}"))
    size_items = [(i, lbl) for _k, i, lbl in sorted(sized)]
    branches.append(Branch("size", "Maximum file size", "radio", tuple(size_items)))
    for field_name, label in (("modified", "Modified within"), ("created", "Created within")):
        # A window resolves to an absolute date the moment it is picked, so the
        # row names that date: "Last 7 days" alone reads as rolling.
        dated = [
            (
                -1 if d is None else d,
                f"{field_name}:{i}",
                lbl if d is None else f"{lbl} — from {_window_start(d).isoformat()}",
            )
            for i, lbl, d in _WINDOWS
        ]
        for custom in _custom_offers(field_name, spec, keep_custom):
            since = custom.removeprefix(f"{CUSTOM}:")
            days = (dt.date.today() - dt.date.fromisoformat(since)).days
            dated.append((days, f"{field_name}:{custom}", f"Since {since}"))
        items = [(i, lbl) for _k, i, lbl in sorted(dated)]
        branches.append(Branch(field_name, label, "radio", tuple(items)))
    beyond = _beyond_the_pickers(spec)
    if beyond:
        # These dimensions have no picker: "Maximum file size" cannot hold a
        # minimum, and "Modified within" cannot hold an upper bound. Without a
        # row the tree looked complete while they filtered.
        branches.append(
            Branch(
                "beyond",
                f"Set in the text form  ({len(beyond)})",
                "actions",
                tuple((f"beyond:{name}", text) for name, text in beyond),
            )
        )
    # An actions branch carries no marker, so a collapsed one has to say in
    # its label whether a rule is set.
    set_rules = sum(1 for v in (spec.frontmatter, spec.expression) if (v or "").strip())
    branches.append(
        Branch(
            "rules",
            "Rules you type" + (f"  ({set_rules} set)" if set_rules else "  (none)"),
            "actions",
            (
                ("rule:frontmatter", _rule_label("Frontmatter rule", spec.frontmatter)),
                ("rule:expression", _rule_label("Custom rule", spec.expression)),
            ),
        )
    )
    return branches


def selection_for(
    spec: FilterSpec, *, gitignore: bool = True, fndignore: bool = True
) -> tuple[set[str], set[str]]:
    """``(selected, excluded)`` item ids matching ``spec``.

    The two ignore flags are passed separately: they choose which files are
    read rather than filtering one, so they are not part of the predicate
    spec the gate compiles.
    """
    selected: set[str] = {
        f"tag:{source}:{t}" for source, tags in spec.tag_includes.items() for t in tags
    }
    excluded: set[str] = {
        f"tag:{source}:{t}" for source, tags in spec.tag_excludes.items() for t in tags
    }
    selected |= {f"kind:{k}" for k in spec.kinds}
    # ``kinds`` empty means every type, which the tree shows as nothing ticked.
    if gitignore:
        selected.add("ignore:git")
    if fndignore:
        selected.add("ignore:fnd")
    selected.add(f"size:{_size_id(spec.max_size)}")
    selected.add(f"modified:{_window_id(spec.modified_after)}")
    selected.add(f"created:{_window_id(spec.created_after)}")
    return selected, excluded


def _tags_from(ids: set[str] | frozenset[str]) -> dict[str, tuple[str, ...]]:
    """``tag:<source>:<value>`` item ids back into the source-keyed mapping.

    Split at most twice: a tag value may itself contain a colon.
    """
    out: dict[str, list[str]] = {}
    for item in ids:
        if not item.startswith("tag:"):
            continue
        _, source, tag = item.split(":", 2)
        out.setdefault(source, []).append(tag)
    return {source: tuple(sorted(tags)) for source, tags in out.items()}


CUSTOM = "custom"
"""Prefix for the row shown when a bound is not one of the offered options.

The options set a bound; the bound itself is an arbitrary number or date.
Mapping an unmatched value back to "any" let an unrelated toggle delete it,
and made a window stop matching two days after it was picked.

The id carries the value — ``size:custom:5000000`` — rather than meaning
"whatever the spec holds". The tree's labels are built when it is rebuilt
while a selection is resolved as it is made, so an id that referred to the
current spec resolved a row still reading "Up to 5 MB" to a bound the user
had since changed.
"""


def _human_size(value: int) -> str:
    for unit, step in (("GB", 1_000_000_000), ("MB", 1_000_000), ("kB", 1_000)):
        if value >= step:
            return f"{value / step:g} {unit}"
    return f"{value} bytes"


def _size_id(value: int | None) -> str:
    if value is None:
        return "any"
    return next((i for i, _l, v in _SIZES if v == value), f"{CUSTOM}:{value}")


def _window_start(days: int) -> dt.date:
    """The absolute date a window resolves to today."""
    return dt.date.today() - dt.timedelta(days=days)


def _window_id(value: dt.date | None) -> str:
    if value is None:
        return "any"
    days = (dt.date.today() - value).days
    return next(
        (i for i, _l, d in _WINDOWS if d is not None and abs(d - days) <= 1),
        f"{CUSTOM}:{value.isoformat()}",
    )


def custom_ids(spec: FilterSpec) -> dict[str, str]:
    """Branch id → the custom bound it currently holds, if any."""
    holds = {
        "size": _size_id(spec.max_size),
        "modified": _window_id(spec.modified_after),
        "created": _window_id(spec.created_after),
    }
    return {branch: i for branch, i in holds.items() if i.startswith(f"{CUSTOM}:")}


def _custom_offers(
    branch: str, spec: FilterSpec, keep: Mapping[str, str] | None
) -> tuple[str, ...]:
    """The custom rows a branch shows: its own bound first, then a kept one."""
    ids = (custom_ids(spec).get(branch), (keep or {}).get(branch))
    return tuple(dict.fromkeys(i for i in ids if i))


def _custom_value(selected: set[str] | frozenset[str], field: str) -> str | None:
    """The value carried by a selected ``<field>:custom:<value>`` id."""
    prefix = f"{field}:{CUSTOM}:"
    return next((i[len(prefix) :] for i in selected if i.startswith(prefix)), None)


def apply_selection(
    spec: FilterSpec,
    selected: set[str] | frozenset[str],
    excluded: set[str] | frozenset[str],
    offered: set[str] | frozenset[str] | None = None,
) -> tuple[FilterSpec, bool, bool]:
    """``(spec, respect_gitignore, respect_fndignore)`` matching the tree.

    ``offered`` is the set of kind ids the tree actually showed. The tree lists
    only the types a source contains, so ticking every visible box is the user
    saying "all of them" even though the registry has more.
    """
    picked = {i.removeprefix("kind:") for i in selected if i.startswith("kind:")}
    # Every box ticked means "every type", not the list of types that exist
    # today: freezing it meant a PDF added tomorrow was never indexed, while
    # leaving the branch untouched indexed it, and both read as "all types".
    # `AddCollectionWizard._set_includes` already collapses the same way.
    shown = {i.removeprefix("kind:") for i in offered if i.startswith("kind:")} if offered else None
    everything = shown or set(ALL_KIND_IDS)
    kinds = () if picked and picked >= everything else tuple(sorted(picked))
    keep = _tags_from(selected)
    tags = _tags_from(excluded)
    today = dt.date.today()

    custom_size = _custom_value(selected, "size")
    if custom_size is not None:
        max_size = int(custom_size)
    else:
        max_size = next(
            (v for i, _l, v in _SIZES if f"size:{i}" in selected and v is not None),
            None,
        )
    bounds: dict[str, dt.date | None] = {}
    for field_name in ("modified", "created"):
        custom_date = _custom_value(selected, field_name)
        if custom_date is not None:
            bounds[f"{field_name}_after"] = dt.date.fromisoformat(custom_date)
            continue
        days = next(
            (d for i, _l, d in _WINDOWS if f"{field_name}:{i}" in selected and d is not None),
            None,
        )
        bounds[f"{field_name}_after"] = today - dt.timedelta(days=days) if days else None

    updated = replace(
        spec,
        kinds=kinds,
        include_tags=keep,
        exclude_tags=tags,
        max_size=max_size,
        modified_after=bounds["modified_after"],
        created_after=bounds["created_after"],
    )
    return updated, "ignore:git" in selected, "ignore:fnd" in selected
