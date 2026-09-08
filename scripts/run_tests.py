"""Run pytest one at a time, with a worker count sized to spare capacity.

Two suites on one machine starve each other: at 97% CPU busy and 100 MB free
RAM, a test asserting on its own CPU share failed 1 run in 3, under xdist and
serially alike. The lock removes the overlap, the worker count keeps a single
run inside spare capacity, and both are advisory: pytest run directly is
unaffected. The lock is per-user, not repo-local, because the contention this
exists to stop comes from sibling worktrees with their own ``.git``. Workers
are sized after the lock is held, so a queued run measures the machine it will
actually get rather than the one it is waiting behind.

An interrupt during the wait relies on ``KeyboardInterrupt`` being a
``BaseException``: widening the guard below to ``except BaseException`` would
make a queued run uninterruptible.

``FND_TEST_WORKERS`` forces the worker count and ``FND_TEST_NO_LOCK`` skips the
gate; the two are independent. An explicit ``-n`` suppresses the sizing only,
and still queues behind the lock.
"""

from __future__ import annotations

import contextlib
import errno
import math
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Generator, Sequence
from pathlib import Path
from typing import IO

# -n 10 measured slower than -n 8 on this 10-core box (6:01 vs 5:24); 6 costs
# a further 41s and leaves four cores for the rest of the machine.
WORKER_CEILING = 6
# Peak RSS of a worker plus its extract-pool child, measured at ~1.0 GB.
GB_PER_WORKER = 1.2
LOCK_TIMEOUT_SECONDS = 1800
# Set once held, so tests/conftest.py's gate does not queue behind us.
LOCK_ENV = "FND_TEST_LOCK_HELD"


def _notify(message: str) -> None:
    """pre-commit captures hook output and prints it only on failure, so a
    wait reaches nobody and a queued push reads as a hang. The terminal
    bypasses that buffer."""
    device = "CONOUT$" if sys.platform == "win32" else "/dev/tty"
    try:
        with open(device, "w") as terminal:
            terminal.write(f"{message}\n")
            terminal.flush()
        return
    except OSError:
        print(message, file=sys.stderr, flush=True)


def _free_gb() -> float:
    """Memory the OS can hand out without compressing or swapping."""
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return float("inf")
        page = 4096
        counts: dict[str, int] = {}
        for line in out.splitlines():
            if "page size of" in line:
                page = int(line.split("page size of")[1].split()[0])
            key, _, value = line.partition(":")
            value = value.strip().rstrip(".")
            if value.isdigit():
                counts[key.strip()] = int(value)
        pages = sum(counts.get(k, 0) for k in ("Pages free", "Pages purgeable", "Pages inactive"))
        return pages * page / 1024**3 if pages else float("inf")
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024**2
    return float("inf")


def _busy_cores(ncpu: int) -> float:
    """Cores in use now. macOS load average reads far above true occupancy
    (12.25 against 3.26 measured), and lags a machine that just got busy, so
    it is the fallback rather than a cheap short-circuit. The sample costs 2.2s."""
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["top", "-l", "2", "-n", "0"], capture_output=True, text=True, timeout=30
            ).stdout
            usage = [ln for ln in out.splitlines() if ln.startswith("CPU usage")][-1]
            return ncpu * (1.0 - float(usage.split(",")[-1].strip().split("%")[0]) / 100.0)
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
    try:
        return os.getloadavg()[0]
    except OSError:
        return ncpu / 2.0


def pick_workers() -> int:
    """Workers that fit in both spare CPU and free RAM, capped at the ceiling."""
    forced = os.environ.get("FND_TEST_WORKERS")
    if forced:
        return max(1, int(forced))
    ncpu = os.cpu_count() or 4
    if sys.platform == "win32":
        return max(1, min(WORKER_CEILING, ncpu // 2))
    allowed = min(ncpu - _busy_cores(ncpu), _free_gb() / GB_PER_WORKER)
    return max(1, min(WORKER_CEILING, math.floor(allowed)))


def _try_acquire(handle: IO[str]) -> bool:
    """False while another run holds the lock. OSError means the lock itself is
    unusable, which must not be mistaken for contention and waited out."""
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EDEADLK):
                return False
            raise
        return True

    import fcntl

    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _lock_path() -> Path:
    """gettempdir() is already per-user on macOS and Windows. On Linux it is
    /tmp, where the second account to run fails open on the first one's file."""
    if sys.platform == "win32":
        who = os.environ.get("USERNAME", "user")
    else:
        who = str(os.getuid())
    return Path(tempfile.gettempdir()) / f"fnd-pytest-{who}.lock"


@contextlib.contextmanager
def _machine_lock() -> Generator[None]:
    if os.environ.get("FND_TEST_NO_LOCK"):
        yield
        return
    try:
        handle = _lock_path().open("a+")
    except OSError as exc:
        _notify(f"test lock unavailable ({exc}); running unsynchronised")
        os.environ[LOCK_ENV] = "1"
        yield
        return
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    announced = False
    try:
        while True:
            try:
                if _try_acquire(handle):
                    break
            except OSError as exc:
                _notify(f"test lock unusable ({exc}); running unsynchronised")
                break
            if time.monotonic() > deadline:
                _notify("test lock still held after 30m; running anyway")
                break
            if not announced:
                _notify("another test run is in progress, waiting...")
                announced = True
            time.sleep(2.0)
        # However the wait ended: a timeout that left this unset spawned a
        # second thirty-minute wait in the child, for sixty in total.
        os.environ[LOCK_ENV] = "1"
        yield
    finally:
        handle.close()


def _wants_workers(args: Sequence[str]) -> bool:
    """An explicit -n wins, and injecting one under `-p no:xdist` exits 4."""
    if any(a.startswith(("-n", "--numprocesses")) for a in args):
        return False
    return not any("no:xdist" in a for a in args)


def main() -> int:
    args = list(sys.argv[1:])
    try:
        with _machine_lock():
            if _wants_workers(args):
                workers = pick_workers()
                # Announced even at one worker: silence is what _notify exists
                # to prevent, and a serial run is the longest silence there is.
                _notify(f"pytest: {workers} worker{'s' if workers > 1 else ''}")
                if workers > 1:
                    # loadfile keeps a module's tests on one worker, which the
                    # module-scoped fixture in test_query_acceptance.py wants.
                    # Costs 19s against --dist load.
                    args = ["-n", str(workers), "--dist", "loadfile", *args]
            status = subprocess.call([sys.executable, "-m", "pytest", *args])
            # A signal death returns -N here, which sys.exit wraps to 256-N:
            # a killed run reported 247 rather than the shell's 137.
            return status if status >= 0 else 128 - status
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
