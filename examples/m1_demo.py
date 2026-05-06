"""Milestone-1 boundary demo for `governing-landscape`.

Exercises the Rust→Python interface end to end on a synthetic two-instance
sparse cloud. No GPU, no real imagery, no gsplat. Once the Moulay Brahim
imagery is acquired (`data/sites/moulay-brahim/manifest.toml`) and the
`[splat]` extra is installed, `examples/m1_gsplat_train.py` will replace
the synthetic cloud with a COLMAP / hloc reconstruction.

Run:
    cd crates/governing-landscape-py
    uv venv && source .venv/bin/activate
    uv pip install maturin numpy
    maturin develop --release
    python ../../examples/m1_demo.py
"""
from __future__ import annotations

import numpy as np

import governing_landscape as gl


def synthetic_two_instance_cloud(
    n_per_instance: int = 32,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Two well-separated Gaussian clusters."""
    rng = rng or np.random.default_rng(0)
    cluster_a = rng.normal(loc=[0.0, 0.0, 0.0], scale=0.3, size=(n_per_instance, 3))
    cluster_b = rng.normal(loc=[10.0, 0.0, 0.0], scale=0.3, size=(n_per_instance, 3))
    means = np.concatenate([cluster_a, cluster_b]).astype(np.float32)
    opacities = rng.uniform(0.3, 0.9, size=2 * n_per_instance).astype(np.float32)
    colours = rng.uniform(0.0, 1.0, size=(2 * n_per_instance, 3)).astype(np.float32)
    psi = np.concatenate(
        [np.zeros(n_per_instance, np.uint32), np.ones(n_per_instance, np.uint32)]
    )
    return means, opacities, colours, psi


def main() -> None:
    means, opacities, colours, psi = synthetic_two_instance_cloud()
    feats = gl.geometric_features(means, opacities, colours, psi, n_instances=2)

    print(f"governing-landscape {gl.__version__}")
    print(f"input: {means.shape[0]} Gaussians, {feats.shape[0]} instances")
    print(f"feature shape: {feats.shape} (expected (n_instances, 13))")
    print()
    for j, f in enumerate(feats):
        cx, cy, cz = f[0:3]
        m_xx, m_xy, m_xz, m_yy, m_yz, m_zz = f[3:9]
        v = f[9]
        cr, cg, cb = f[10:13]
        print(
            f"instance {j}: centroid=({cx: .3f}, {cy: .3f}, {cz: .3f}) "
            f"v={v:.3f} colour=({cr:.2f}, {cg:.2f}, {cb:.2f}) "
            f"M_xx={m_xx:.4f}"
        )

    # Sanity checks against the cluster construction.
    assert abs(feats[0, 0]) < 0.5, "instance 0 centroid should be near origin"
    assert abs(feats[1, 0] - 10.0) < 0.5, "instance 1 centroid should be near x=10"
    print("\nSanity checks pass.")


if __name__ == "__main__":
    main()
