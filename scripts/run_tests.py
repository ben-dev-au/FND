"""Run pytest one at a time, with a worker count sized to spare capacity.

Two suites on one machine starve each other: at 97% CPU busy and 100 MB free
RAM, a test asserting on its own CPU share failed 1 run in 3, under xdist and
serially alike. The lock removes the overlap, the worker count keeps a single
run inside spare capacity, and both are advisory: pytest run directly is
unaffected. The lock is machine-wide, not repo-local, because the contention
this exists to stop comes from sibling worktrees with their own ``.git``.

``FND_TEST_WORKERS`` forces the worker count; ``FND_TEST_NO_LOCK`` skips the
gate. An explicit ``-n`` on the command line disables both defaults.
"""

from __future__ import annotations

import contextlib
import math
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import IO

# -n 10 measured slower than -n 8 on this 10-core box (6:01 vs 5:24); 6 costs
# a further 41s and leaves four cores for the rest of the machine.
WORKER_CEILING = 6
# Peak RSS of a worker plus its extract-pool child, measured at ~1.0 GB.
GB_PER_WORKER = 1.2
LOCK_TIMEOUT_SECONDS = 1800


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
        return pages * page / 1024**3
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024**2
    return float("inf")


def _busy_cores(ncpu: int) -> float:
    """Cores in use now. An instantaneous sample beats the 1-minute load
    average, which lags a run that started seconds ago."""
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
        return min(WORKER_CEILING, max(2, ncpu // 2))
    allowed = min(ncpu - _busy_cores(ncpu), _free_gb() / GB_PER_WORKER)
    return max(1, min(WORKER_CEILING, math.floor(allowed)))


def _acquire(handle: IO[str]) -> None:
    """Raises OSError when another run holds the lock."""
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextlib.contextmanager
def _machine_lock() -> Iterator[None]:
    if os.environ.get("FND_TEST_NO_LOCK"):
        yield
        return
    handle = (Path(tempfile.gettempdir()) / "fnd-pytest.lock").open("w")
    handle.write("x")
    handle.flush()
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    announced = False
    try:
        while True:
            try:
                _acquire(handle)
                break
            except OSError:
                if time.monotonic() > deadline:
                    print("lock still held after 30m; running anyway", file=sys.stderr)
                    break
                if not announced:
                    print("another test run is in progress, waiting...", file=sys.stderr)
                    announced = True
                time.sleep(2.0)
        yield
    finally:
        handle.close()


def main() -> int:
    args = sys.argv[1:]
    if not any(a.startswith(("-n", "--numprocesses")) for a in args):
        workers = pick_workers()
        if workers > 1:
            print(f"pytest: {workers} workers", file=sys.stderr)
            args = ["-n", str(workers), "--dist", "load", *args]
    with _machine_lock():
        return subprocess.call([sys.executable, "-m", "pytest", *args])


if __name__ == "__main__":
    sys.exit(main())
