"""Worker-injection rules for the pre-push wrapper (scripts/run_tests.py)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_wrapper() -> ModuleType:
    """scripts/ is not a package, so the wrapper is loaded by path."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tests.py"
    spec = importlib.util.spec_from_file_location("_fnd_run_tests", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_WRAPPER = _load_wrapper()


@pytest.mark.parametrize(
    ("args", "wanted"),
    [
        ([], True),
        (["-q", "-m", "not slow", "--testmon-forceselect"], True),
        # An explicit worker count wins over the sizing.
        (["-n", "3"], False),
        (["-n3"], False),
        (["-nauto"], False),
        (["--numprocesses=4"], False),
        # Injecting -n while xdist is disabled exits 4 with no tests run.
        (["-p", "no:xdist"], False),
        # Flags that merely start like -n, or disable another plugin.
        (["-p", "no:randomly"], True),
        (["--noconftest"], True),
        (["--no-header"], True),
    ],
)
def test_worker_injection_rules(args: list[str], wanted: bool) -> None:
    """Injection is suppressed by an explicit -n and by a disabled xdist."""
    assert _WRAPPER._wants_workers(args) is wanted


def test_forced_worker_count_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    """FND_TEST_WORKERS overrides sizing without sampling the machine."""
    monkeypatch.setenv("FND_TEST_WORKERS", "3")
    assert _WRAPPER.pick_workers() == 3


def test_forced_worker_count_never_drops_below_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A zero or negative override would make pytest reject the -n it is given."""
    monkeypatch.setenv("FND_TEST_WORKERS", "0")
    assert _WRAPPER.pick_workers() == 1


@pytest.mark.parametrize(
    ("status", "wanted"),
    [(0, 0), (1, 1), (4, 4), (-9, 137), (-15, 143), (-16, 144)],
)
def test_signal_deaths_use_the_shell_convention(
    status: int, wanted: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """subprocess returns -N for a signal; sys.exit would wrap that to 256-N."""
    monkeypatch.setenv("FND_TEST_NO_LOCK", "1")
    monkeypatch.setenv("FND_TEST_WORKERS", "1")
    # _notify writes to the tty, which pytest cannot capture.
    monkeypatch.setattr(_WRAPPER, "_notify", lambda message: None)
    monkeypatch.setattr(_WRAPPER.subprocess, "call", lambda cmd: status)
    monkeypatch.setattr(_WRAPPER.sys, "argv", ["run_tests.py", "-q"])
    assert _WRAPPER.main() == wanted


@pytest.mark.parametrize(
    ("workers", "announced"),
    [(1, "pytest: 1 worker"), (2, "pytest: 2 workers")],
)
def test_every_sized_run_announces_its_worker_count(
    workers: int, announced: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silence reads as a hang, and a serial run is the longest silence."""
    notices: list[str] = []
    commands: list[list[str]] = []

    def _record(cmd: list[str]) -> int:
        commands.append(cmd)
        return 0

    monkeypatch.setenv("FND_TEST_NO_LOCK", "1")
    monkeypatch.setenv("FND_TEST_WORKERS", str(workers))
    monkeypatch.setattr(_WRAPPER, "_notify", notices.append)
    monkeypatch.setattr(_WRAPPER.subprocess, "call", _record)
    monkeypatch.setattr(_WRAPPER.sys, "argv", ["run_tests.py", "-q"])

    assert _WRAPPER.main() == 0
    assert notices == [announced]
    assert ("-n" in commands[0]) is (workers > 1)


def test_an_explicit_worker_count_announces_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """No sizing decision was made, so there is no honest number to report."""
    notices: list[str] = []
    monkeypatch.setenv("FND_TEST_NO_LOCK", "1")
    monkeypatch.setattr(_WRAPPER, "_notify", notices.append)
    monkeypatch.setattr(_WRAPPER.subprocess, "call", lambda cmd: 0)
    monkeypatch.setattr(_WRAPPER.sys, "argv", ["run_tests.py", "-n", "2"])

    assert _WRAPPER.main() == 0
    assert notices == []


def test_the_suite_starts_with_xdist_unregistered() -> None:
    """`-p no:xdist` leaves xdist installed but unregistered, so conftest's
    xdist hook must be optional or collection dies before any test runs."""
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:xdist",
            "-q",
            "--collect-only",
            "tests/test_smoke.py",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "FND_TEST_NO_LOCK": "1"},
    )
    output = result.stdout + result.stderr
    assert "PluginValidationError" not in output, output[-1500:]
    assert result.returncode == 0, output[-1500:]


def test_the_lock_path_is_per_user() -> None:
    """Linux hands every account the same /tmp, where the second one to run
    hits the first one's file and fails open instead of queueing."""
    path = _WRAPPER._lock_path()
    who = os.environ.get("USERNAME", "user") if sys.platform == "win32" else str(os.getuid())
    assert who in path.name


def test_a_timed_out_wait_still_bars_the_child_from_queueing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper gives up after 30 minutes and runs anyway; without the
    handshake the child's own gate then waits 30 more."""
    monkeypatch.delenv("FND_TEST_NO_LOCK", raising=False)
    monkeypatch.delenv(_WRAPPER.LOCK_ENV, raising=False)
    monkeypatch.setattr(_WRAPPER, "LOCK_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(_WRAPPER, "_try_acquire", lambda handle: False)
    monkeypatch.setattr(_WRAPPER, "_notify", lambda message: None)

    with _WRAPPER._machine_lock():
        assert os.environ.get(_WRAPPER.LOCK_ENV) == "1"


def test_an_unusable_lock_also_bars_the_child(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same handshake on the path where the lock itself is broken, so the
    child reports it once rather than rediscovering it."""
    monkeypatch.delenv("FND_TEST_NO_LOCK", raising=False)
    monkeypatch.delenv(_WRAPPER.LOCK_ENV, raising=False)
    monkeypatch.setattr(_WRAPPER, "_notify", lambda message: None)

    def _broken(handle: object) -> bool:
        raise OSError(9, "bad file descriptor")

    monkeypatch.setattr(_WRAPPER, "_try_acquire", _broken)
    with _WRAPPER._machine_lock():
        assert os.environ.get(_WRAPPER.LOCK_ENV) == "1"
