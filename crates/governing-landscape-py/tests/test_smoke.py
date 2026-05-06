import numpy as np
import pytest

import governing_landscape as gl


def test_version():
    assert isinstance(gl.__version__, str)
    assert gl.__version__.count(".") == 2


def test_geometric_features_single_gaussian():
    means = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
    opacities = np.array([0.7], dtype=np.float32)
    colours = np.array([[0.5, 0.5, 0.5]], dtype=np.float32)
    psi = np.array([0], dtype=np.uint32)

    feats = gl.geometric_features(means, opacities, colours, psi, 1)
    assert feats.shape == (1, 13)
    np.testing.assert_array_equal(feats[0, 0:3], [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(feats[0, 3:9], np.zeros(6, dtype=np.float32))
    assert feats[0, 9] == pytest.approx(0.7)
    np.testing.assert_array_equal(feats[0, 10:13], [0.5, 0.5, 0.5])


def test_geometric_features_two_instances():
    means = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [10.0, 0.0, 0.0], [11.0, 0.0, 0.0]],
        dtype=np.float32,
    )
    opacities = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)
    colours = np.tile(np.array([0.5, 0.5, 0.5], dtype=np.float32), (4, 1))
    psi = np.array([0, 0, 1, 1], dtype=np.uint32)

    feats = gl.geometric_features(means, opacities, colours, psi, 2)
    assert feats.shape == (2, 13)
    np.testing.assert_allclose(feats[0, 0:3], [0.5, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(feats[1, 0:3], [10.5, 0.0, 0.0], atol=1e-6)
    assert feats[0, 9] == pytest.approx(1.0)
    assert feats[1, 9] == pytest.approx(1.0)


def test_geometric_features_opacity_weighted():
    # Centroid biased toward higher-opacity Gaussian.
    means = np.array([[10.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float32)
    opacities = np.array([0.9, 0.1], dtype=np.float32)
    colours = np.array([[0.5, 0.5, 0.5]] * 2, dtype=np.float32)
    psi = np.array([0, 0], dtype=np.uint32)

    feats = gl.geometric_features(means, opacities, colours, psi, 1)
    assert feats[0, 0] == pytest.approx(9.0, rel=1e-6)


def test_geometric_features_validates_shapes():
    means = np.zeros((3, 3), dtype=np.float32)
    opacities = np.zeros(3, dtype=np.float32)
    colours = np.zeros((2, 3), dtype=np.float32)  # wrong length
    psi = np.zeros(3, dtype=np.uint32)
    with pytest.raises(ValueError, match="colours"):
        gl.geometric_features(means, opacities, colours, psi, 1)


def test_geometric_features_validates_opacity_range():
    means = np.zeros((1, 3), dtype=np.float32)
    opacities = np.array([1.5], dtype=np.float32)  # out of range
    colours = np.zeros((1, 3), dtype=np.float32)
    psi = np.zeros(1, dtype=np.uint32)
    with pytest.raises(ValueError, match="opacity"):
        gl.geometric_features(means, opacities, colours, psi, 1)


def test_geometric_features_validates_surjection():
    means = np.zeros((2, 3), dtype=np.float32)
    opacities = np.array([0.5, 0.5], dtype=np.float32)
    colours = np.zeros((2, 3), dtype=np.float32)
    psi = np.array([0, 0], dtype=np.uint32)  # leaves instance 1 empty
    with pytest.raises(ValueError, match="surjective"):
        gl.geometric_features(means, opacities, colours, psi, 2)
