"""Unit tests for examples/_memcage.py.

Tests do NOT re-exec, call systemd-run, or touch /proc — all external
interactions are either injected via arguments or monkeypatched.
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Make examples/ importable regardless of how pytest is invoked.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import _memcage  # type: ignore[missing-import]  # noqa: E402  (import after sys.path manipulation; examples/ not a pyrefly root)

# ---------------------------------------------------------------------------
# Sample /proc/meminfo text for injection
# ---------------------------------------------------------------------------

SAMPLE_MEMINFO = """\
MemTotal:       32768000 kB
MemFree:         1234567 kB
MemAvailable:    8388608 kB
Buffers:          200000 kB
Cached:          4000000 kB
SwapTotal:      49283072 kB
SwapFree:       40000000 kB
"""

# 8388608 kB = 8 GiB exactly
EXPECTED_AVAILABLE_GIB = 8388608 / (1024.0 ** 2)


# ---------------------------------------------------------------------------
# mem_available_gib
# ---------------------------------------------------------------------------

class TestMemAvailableGib:
    def test_parses_sample_text(self) -> None:
        result = _memcage.mem_available_gib(SAMPLE_MEMINFO)
        assert abs(result - EXPECTED_AVAILABLE_GIB) < 1e-6

    def test_raises_when_line_missing(self) -> None:
        with pytest.raises(RuntimeError, match="MemAvailable not found"):
            _memcage.mem_available_gib("MemTotal: 32768000 kB\n")

    def test_fractional_kib(self) -> None:
        text = "MemAvailable:    1048576 kB\n"  # 1 GiB exactly
        assert abs(_memcage.mem_available_gib(text) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# cage_budget
# ---------------------------------------------------------------------------

class TestCageBudget:
    def test_default_tier(self) -> None:
        b = _memcage.cage_budget(exclusive=False)
        assert b["max"] == "16G"
        assert b["high"] == "14G"
        assert b["swap_max"] == "2G"
        assert float(b["required_gib"]) == 16.0

    def test_exclusive_tier(self) -> None:
        b = _memcage.cage_budget(exclusive=True)
        assert b["max"] == "24G"
        assert b["high"] == "22G"
        assert b["swap_max"] == "4G"
        assert float(b["required_gib"]) == 24.0

    def test_returns_copy(self) -> None:
        """Mutating the returned dict must not affect subsequent calls."""
        b1 = _memcage.cage_budget(exclusive=False)
        b1["max"] = "MUTATED"
        b2 = _memcage.cage_budget(exclusive=False)
        assert b2["max"] == "16G"


# ---------------------------------------------------------------------------
# build_caged_argv
# ---------------------------------------------------------------------------

class TestBuildCagedArgv:
    def _budget(self) -> dict[str, str | float]:
        return _memcage.cage_budget(exclusive=False)

    def test_starts_with_systemd_run(self) -> None:
        argv = _memcage.build_caged_argv(["python", "foo.py"], self._budget(), label="test")
        assert argv[0] == "systemd-run"

    def test_contains_user_scope_flags(self) -> None:
        argv = _memcage.build_caged_argv(["python", "foo.py"], self._budget(), label="test")
        assert "--user" in argv
        assert "--scope" in argv

    def test_memory_max_flag(self) -> None:
        budget = self._budget()
        argv = _memcage.build_caged_argv(["python", "foo.py"], budget, label="test")
        # -p MemoryMax=16G must appear as two adjacent elements
        idx = argv.index("-p")
        while idx != -1:
            if argv[idx + 1] == f"MemoryMax={budget['max']}":
                break
            try:
                idx = argv.index("-p", idx + 1)
            except ValueError:
                idx = -1
        assert idx != -1, "MemoryMax flag not found in argv"

    def test_memory_high_flag(self) -> None:
        budget = self._budget()
        argv = _memcage.build_caged_argv(["python", "foo.py"], budget, label="test")
        assert f"MemoryHigh={budget['high']}" in argv

    def test_memory_swap_max_flag(self) -> None:
        budget = self._budget()
        argv = _memcage.build_caged_argv(["python", "foo.py"], budget, label="test")
        assert f"MemorySwapMax={budget['swap_max']}" in argv

    def test_separator_then_inner_argv(self) -> None:
        inner = ["python", "script.py", "--arg", "val"]
        argv = _memcage.build_caged_argv(inner, self._budget(), label="test")
        sep_idx = argv.index("--")
        assert argv[sep_idx + 1:] == inner

    def test_description_label(self) -> None:
        argv = _memcage.build_caged_argv(["python"], self._budget(), label="mytest:label")
        assert any("mytest:label" in a for a in argv)

    def test_p_flags_are_separate_elements(self) -> None:
        """Each -p must be followed by key=value as the NEXT element (not combined)."""
        argv = _memcage.build_caged_argv(["python"], self._budget(), label="t")
        p_indices = [i for i, a in enumerate(argv) if a == "-p"]
        assert len(p_indices) >= 3
        for i in p_indices:
            # The next element must be a key=value string (not start with '-')
            assert "=" in argv[i + 1], f"argv[{i+1}]={argv[i+1]!r} is not key=value"

    def test_pure_no_side_effects(self) -> None:
        """Calling the function must not mutate the environment or inner_argv."""
        inner = ["python", "a.py"]
        env_before = dict(os.environ)
        _memcage.build_caged_argv(inner, self._budget(), label="t")
        assert dict(os.environ) == env_before
        assert inner == ["python", "a.py"]


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------

class TestPreflight:
    def test_raises_when_below_floor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Inject 4 GiB available — below the 16 GiB default floor
        monkeypatch.setattr(
            _memcage, "mem_available_gib", lambda meminfo_text=None: 4.0
        )
        with pytest.raises(SystemExit) as exc_info:
            _memcage.preflight(exclusive=False)
        msg = str(exc_info.value)
        assert "16" in msg  # mentions the required floor
        assert "4" in msg   # mentions available amount

    def test_raises_when_below_exclusive_floor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 20 GiB available — above default floor (16) but below exclusive floor (24)
        monkeypatch.setattr(
            _memcage, "mem_available_gib", lambda meminfo_text=None: 20.0
        )
        with pytest.raises(SystemExit):
            _memcage.preflight(exclusive=True)

    def test_passes_when_above_floor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 20 GiB available — above the 16 GiB default floor
        monkeypatch.setattr(
            _memcage, "mem_available_gib", lambda meminfo_text=None: 20.0
        )
        # Must not raise
        _memcage.preflight(exclusive=False)

    def test_passes_exclusive_when_sufficient(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            _memcage, "mem_available_gib", lambda meminfo_text=None: 25.0
        )
        _memcage.preflight(exclusive=True)

    def test_exact_boundary_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Exactly at the floor must NOT raise (< not <=)."""
        monkeypatch.setattr(
            _memcage, "mem_available_gib", lambda meminfo_text=None: 16.0
        )
        _memcage.preflight(exclusive=False)  # should not raise


# ---------------------------------------------------------------------------
# single_instance_lock
# ---------------------------------------------------------------------------

class TestSingleInstanceLock:
    def test_acquires_and_releases(self, tmp_path: pathlib.Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        with _memcage.single_instance_lock(lock_file):
            assert os.path.exists(lock_file)
        # After the context, a new acquisition must succeed (lock released)
        with _memcage.single_instance_lock(lock_file):
            pass

    def test_creates_missing_lock_file(self, tmp_path: pathlib.Path) -> None:
        lock_file = str(tmp_path / "nonexistent.lock")
        assert not os.path.exists(lock_file)
        with _memcage.single_instance_lock(lock_file):
            assert os.path.exists(lock_file)

    def test_raises_when_already_held(self, tmp_path: pathlib.Path) -> None:
        """Acquiring the same lock twice in the same process must raise SystemExit."""
        import fcntl as _fcntl

        lock_file = str(tmp_path / "held.lock")

        # Hold the lock manually in this test so the second attempt in the
        # context manager fails.
        holder_fd = open(lock_file, "a")
        try:
            _fcntl.flock(holder_fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            with pytest.raises(SystemExit) as exc_info:
                with _memcage.single_instance_lock(lock_file):
                    pass  # should not reach here
            assert "lock" in str(exc_info.value).lower()
        finally:
            _fcntl.flock(holder_fd, _fcntl.LOCK_UN)
            holder_fd.close()

    def test_exit_message_contains_path(self, tmp_path: pathlib.Path) -> None:
        import fcntl as _fcntl

        lock_file = str(tmp_path / "pathcheck.lock")
        holder_fd = open(lock_file, "a")
        try:
            _fcntl.flock(holder_fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            with pytest.raises(SystemExit) as exc_info:
                with _memcage.single_instance_lock(lock_file):
                    pass
            assert lock_file in str(exc_info.value)
        finally:
            _fcntl.flock(holder_fd, _fcntl.LOCK_UN)
            holder_fd.close()
