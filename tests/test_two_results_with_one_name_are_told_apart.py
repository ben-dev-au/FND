"""Result rows carry the basename, so `build/out-01.md` and `notes/out-01.md`
were two identical rows.

A hunter asked the question the app is for — "which ones did that drop?" — and
could not answer it from the result list.
"""

from __future__ import annotations

from fnd.tui.results_labels import disambiguated_names


def test_a_unique_name_stays_a_bare_name() -> None:
    names = disambiguated_names(["/vault/notes/alpha.md", "/vault/build/beta.md"])

    assert names["/vault/notes/alpha.md"] == "alpha.md"
    assert names["/vault/build/beta.md"] == "beta.md"


def test_a_shared_name_gains_its_folder() -> None:
    names = disambiguated_names(["/vault/build/out-01.md", "/vault/notes/out-01.md"])

    assert names["/vault/build/out-01.md"] == "build/out-01.md"
    assert names["/vault/notes/out-01.md"] == "notes/out-01.md"


def test_it_keeps_going_until_they_differ() -> None:
    """One folder is not always enough."""
    names = disambiguated_names(["/a/x/gen/out.md", "/b/y/gen/out.md"])

    assert names["/a/x/gen/out.md"] == "x/gen/out.md"
    assert names["/b/y/gen/out.md"] == "y/gen/out.md"


def test_three_of_a_name_all_qualify() -> None:
    names = disambiguated_names(["/v/a/n.md", "/v/b/n.md", "/v/c/n.md"])

    assert set(names.values()) == {"a/n.md", "b/n.md", "c/n.md"}


def test_only_the_shared_names_grow() -> None:
    """The control: qualifying every row would cost width for nothing."""
    names = disambiguated_names(["/v/a/n.md", "/v/b/n.md", "/v/deep/other.md"])

    assert names["/v/deep/other.md"] == "other.md"


def test_the_same_path_twice_is_not_its_own_rival() -> None:
    """One file listed once: a set of one cannot need qualifying."""
    names = disambiguated_names(["/v/a/n.md"])

    assert names["/v/a/n.md"] == "n.md"
