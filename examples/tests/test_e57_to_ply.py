"""Unit tests for voxel_downsample in e57_to_ply.

These tests import only the pure voxel_downsample function and require neither
pye57 nor any real e57 file.  The import of e57_to_ply itself does NOT trigger
the `import pye57` guard because that guard lives inside convert() and main(),
not at module level.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Allow importing e57_to_ply from the examples/ directory without installing it.
_EXAMPLES = Path(__file__).resolve().parent.parent
if str(_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES))

from e57_to_ply import voxel_downsample  # type: ignore[missing-import]  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pts(*rows: tuple[float, ...]) -> np.ndarray:
    return np.array(rows, dtype=np.float64)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVoxelDownsample:
    def test_many_points_in_one_voxel_collapse_to_one(self) -> None:
        """Points inside the same voxel must reduce to exactly 1."""
        voxel = 1.0
        # All points within the unit voxel [0,1)^3
        pts = _pts(
            (0.1, 0.1, 0.1),
            (0.2, 0.3, 0.4),
            (0.9, 0.9, 0.9),
            (0.5, 0.5, 0.5),
        )
        result = voxel_downsample(pts, voxel)
        assert result.shape == (1, 3)

    def test_distinct_voxels_all_preserved(self) -> None:
        """One point per distinct voxel: all must survive."""
        voxel = 1.0
        pts = _pts(
            (0.5, 0.5, 0.5),   # voxel (0,0,0)
            (1.5, 0.5, 0.5),   # voxel (1,0,0)
            (0.5, 1.5, 0.5),   # voxel (0,1,0)
            (0.5, 0.5, 1.5),   # voxel (0,0,1)
        )
        result = voxel_downsample(pts, voxel)
        assert result.shape == (4, 3)

    def test_order_independence(self) -> None:
        """The SET of kept voxel-keys must be the same regardless of input order."""
        voxel = 1.0
        pts = _pts(
            (0.1, 0.1, 0.1),   # voxel (0,0,0)
            (1.1, 0.1, 0.1),   # voxel (1,0,0)
            (0.9, 0.9, 0.9),   # voxel (0,0,0) — duplicate key
        )
        result_fwd = voxel_downsample(pts, voxel)
        result_rev = voxel_downsample(pts[::-1], voxel)

        # Both should have 2 unique voxels
        assert result_fwd.shape[0] == 2
        assert result_rev.shape[0] == 2

        # The voxel keys (floored xyz/voxel) must be the same set
        def voxel_keys(arr: np.ndarray) -> set[tuple[int, int, int]]:
            import math
            inv = 1.0 / voxel
            return {
                (math.floor(r[0] * inv), math.floor(r[1] * inv), math.floor(r[2] * inv))
                for r in arr
            }

        assert voxel_keys(result_fwd) == voxel_keys(result_rev)

    def test_with_intensity_column_preserved(self) -> None:
        """Nx4 input (xyz+intensity) is handled and Mx4 is returned."""
        voxel = 1.0
        pts = _pts(
            (0.1, 0.1, 0.1, 0.8),   # voxel (0,0,0)
            (0.2, 0.2, 0.2, 0.3),   # voxel (0,0,0) — same key
            (1.1, 0.1, 0.1, 0.5),   # voxel (1,0,0)
        )
        result = voxel_downsample(pts, voxel)
        assert result.shape == (2, 4)

    def test_single_point_returns_itself(self) -> None:
        """A single point should be returned unchanged."""
        pts = _pts((3.7, -1.2, 0.0))
        result = voxel_downsample(pts, 0.1)
        assert result.shape == (1, 3)
        np.testing.assert_array_almost_equal(result[0], pts[0])

    def test_empty_array_returns_empty(self) -> None:
        """Zero-length input should yield zero-length output."""
        pts = np.empty((0, 3), dtype=np.float64)
        result = voxel_downsample(pts, 0.05)
        assert result.shape == (0, 3)

    def test_small_voxel_keeps_more_points(self) -> None:
        """Smaller voxel = finer grid = more unique voxels from spread points."""
        pts = _pts(
            (0.0, 0.0, 0.0),
            (0.06, 0.0, 0.0),
            (0.12, 0.0, 0.0),
        )
        result_coarse = voxel_downsample(pts, 0.5)   # all in one voxel
        result_fine = voxel_downsample(pts, 0.05)    # each in its own voxel

        assert result_coarse.shape[0] == 1
        assert result_fine.shape[0] == 3

    def test_invalid_shape_raises(self) -> None:
        pts = np.ones((5, 2))  # wrong ncols
        with pytest.raises(ValueError, match="Nx3 or Nx4"):
            voxel_downsample(pts, 0.1)

    def test_invalid_voxel_raises(self) -> None:
        pts = _pts((1.0, 2.0, 3.0))
        with pytest.raises(ValueError, match="voxel must be"):
            voxel_downsample(pts, 0.0)
