"""Memory-cage guard for the reconstruction pipeline.

Re-exec's the current Python process under a transient cgroup-v2 scope via
``systemd-run --user --scope``.  ``MemorySwapMax`` is the load-bearing setting:
capping swap converts a memory overrun into a clean, in-cgroup OOM-kill instead
of a 47 GiB swap death-spiral that takes down the whole machine.

Usage (from a script's ``main``):

    import _memcage
    _memcage.reexec_caged_if_needed(args.exclusive, label="colmap:site:block")

The cage is mandatory.  If ``systemd-run`` is not available the script refuses
to run — we do NOT fall back to ``RLIMIT_AS`` because COLMAP mmap's its DB and
``RLIMIT_AS`` mis-counts virtual address space and breaks it.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import shutil
import sys
from collections.abc import Generator
from typing import Literal  # noqa: F401 — used for documentation clarity

# ---------------------------------------------------------------------------
# Sentinel environment variable
# ---------------------------------------------------------------------------

GL_CAGED_ENV: Literal["GL_CAGED"] = "GL_CAGED"

# ---------------------------------------------------------------------------
# Budget tiers
# ---------------------------------------------------------------------------

_BUDGETS: dict[bool, dict[str, str | float]] = {
    # default: co-tenant cage, 16 GiB floor
    False: {"max": "16G", "high": "14G", "swap_max": "2G", "required_gib": 16.0},
    # exclusive: single-job cage, 24 GiB floor
    True:  {"max": "24G", "high": "22G", "swap_max": "4G", "required_gib": 24.0},
}


def cage_budget(exclusive: bool) -> dict[str, str | float]:
    """Return ``{'max', 'high', 'swap_max', 'required_gib'}`` for the chosen tier.

    Args:
        exclusive: When ``True`` returns the 24 GiB exclusive tier;
                   when ``False`` returns the 16 GiB default co-tenant tier.
    """
    return dict(_BUDGETS[exclusive])


# ---------------------------------------------------------------------------
# Memory availability
# ---------------------------------------------------------------------------

def mem_available_gib(meminfo_text: str | None = None) -> float:
    """Return available RAM in GiB.

    Reads ``/proc/meminfo`` unless *meminfo_text* is supplied (useful in tests).
    Parses the ``MemAvailable:`` line which is in kB.

    Raises:
        RuntimeError: if the ``MemAvailable`` line is not found.
    """
    if meminfo_text is None:
        with open("/proc/meminfo", encoding="ascii") as fh:
            meminfo_text = fh.read()

    for line in meminfo_text.splitlines():
        if line.startswith("MemAvailable:"):
            # Format: "MemAvailable:    7654321 kB"
            parts = line.split()
            kb = float(parts[1])
            return kb / (1024.0 ** 2)

    raise RuntimeError("MemAvailable not found in meminfo text")


# ---------------------------------------------------------------------------
# systemd-run availability
# ---------------------------------------------------------------------------

def have_systemd_run() -> bool:
    """Return ``True`` if ``systemd-run`` is found on ``PATH``."""
    return shutil.which("systemd-run") is not None


# ---------------------------------------------------------------------------
# Argv builder (pure)
# ---------------------------------------------------------------------------

def build_caged_argv(
    inner_argv: list[str],
    budget: dict[str, str | float],
    *,
    label: str,
) -> list[str]:
    """Build the ``systemd-run`` wrapper argv.

    Pure function — no side effects, safe to unit-test.

    Args:
        inner_argv: The argv of the process to cage (e.g. ``[sys.executable, *sys.argv]``).
        budget:     A budget dict as returned by :func:`cage_budget`.
        label:      Human-readable description shown in ``systemctl status`` output.

    Returns:
        A list of strings suitable for passing to :func:`os.execvp`.
    """
    return [
        "systemd-run",
        "--user",
        "--scope",
        "--quiet",
        "--collect",
        f"--description={label}",
        "-p", "MemoryAccounting=yes",
        "-p", f"MemoryMax={budget['max']}",
        "-p", f"MemoryHigh={budget['high']}",
        "-p", f"MemorySwapMax={budget['swap_max']}",
        "--",
        *inner_argv,
    ]


# ---------------------------------------------------------------------------
# Pre-flight check
# ---------------------------------------------------------------------------

def preflight(exclusive: bool, min_free_gib: float | None = None) -> None:
    """Print the chosen budget and abort if available RAM is insufficient.

    The cage's ``MemoryMax`` (16/24 GiB) is a *ceiling*, not a reservation. By
    default the start gate requires the full tier floor free, so a job never
    forces other processes into swap. On a chronically busy box that makes small
    validation jobs impossible to start; ``min_free_gib`` is a conscious operator
    override that lowers ONLY the start gate — the MemoryMax ceiling and the
    MemorySwapMax clean-kill protection are unchanged.

    Args:
        exclusive:    Selects which budget tier to use.
        min_free_gib: If given, the start-gate floor in GiB; otherwise the tier's
                      full required floor (16 default / 24 exclusive).

    Raises:
        SystemExit: if available RAM is below the effective floor.
    """
    budget = cage_budget(exclusive)
    tier_name = "exclusive" if exclusive else "default"
    tier_floor: float = float(budget["required_gib"])
    required = tier_floor if min_free_gib is None else float(min_free_gib)
    override = "" if min_free_gib is None else "  (operator min-free override)"

    print(
        f"[memcage] budget tier={tier_name}  "
        f"MemoryMax={budget['max']}  MemoryHigh={budget['high']}  "
        f"MemorySwapMax={budget['swap_max']}  start_floor={required:.0f} GiB{override}"
    )

    available = mem_available_gib()
    print(f"[memcage] MemAvailable={available:.2f} GiB")

    if available < required:
        raise SystemExit(
            f"[memcage] ABORT: need {required:.0f} GiB free RAM but only "
            f"{available:.2f} GiB is available.\n"
            f"  Hints:\n"
            f"    • Free RAM (close browsers, IDEs, large builds)\n"
            f"    • Reconstruct a smaller image subset / single block\n"
            f"    • Pause a concurrent big build (cargo, etc.) and retry\n"
            f"    • For a small/validation block on a busy box, lower the start "
            f"gate with --min-free-gib N (ceiling + swap cap still apply)"
        )


# ---------------------------------------------------------------------------
# Re-exec into the cage
# ---------------------------------------------------------------------------

def reexec_caged_if_needed(
    exclusive: bool, *, label: str, min_free_gib: float | None = None
) -> None:
    """Re-exec the current process inside a cgroup-v2 memory cage if not already caged.

    No-op when the :data:`GL_CAGED_ENV` sentinel is already set in the
    environment (prevents infinite re-exec loops).

    If ``systemd-run`` is not available this raises :class:`SystemExit` — we do
    NOT fall back to ``RLIMIT_AS``.

    After a successful exec this function never returns; control passes to the
    new child process.

    Args:
        exclusive:    Selects which budget tier to use.
        label:        Passed through to :func:`build_caged_argv` as the scope description.
        min_free_gib: Conscious operator override for the preflight start gate
                      (see :func:`preflight`); ``None`` keeps the strict tier floor.
    """
    if os.environ.get(GL_CAGED_ENV):
        # Already inside the cage — nothing to do.
        return

    if not have_systemd_run():
        raise SystemExit(
            "[memcage] ABORT: the memory cage is mandatory and requires "
            "'systemd-run' (from systemd), which was not found on PATH.\n"
            "  This script does NOT fall back to RLIMIT_AS because COLMAP "
            "mmap's its DB and RLIMIT_AS breaks it.\n"
            "  Install systemd (Fedora: already present) or run on a "
            "systemd-based host."
        )

    preflight(exclusive, min_free_gib)

    budget = cage_budget(exclusive)
    inner_argv: list[str] = [sys.executable, *sys.argv]
    caged_argv = build_caged_argv(inner_argv, budget, label=label)

    # Set the sentinel so the re-exec'd child skips this block.
    os.environ[GL_CAGED_ENV] = "1"

    print(f"[memcage] re-exec'ing under cgroup scope: {' '.join(caged_argv[:6])} …")
    os.execvp(caged_argv[0], caged_argv)  # never returns on success


# ---------------------------------------------------------------------------
# Single-instance lock
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def single_instance_lock(lock_path: str) -> Generator[None, None, None]:
    """Acquire an exclusive non-blocking flock on *lock_path*.

    Creates the lock file if it does not exist.  Releases the lock on context
    exit (even if an exception is raised).

    Args:
        lock_path: Path to the lock file.

    Raises:
        SystemExit: if another process already holds the lock.
    """
    fd = open(lock_path, "a")  # noqa: WPS515 — intentionally kept open for the lock lifetime
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fd.close()
            raise SystemExit(
                f"[memcage] ABORT: another reconstruction job holds the lock at {lock_path!r}.\n"
                f"  Wait for it to finish, or remove the lock file if the previous job crashed."
            )
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        fd.close()
