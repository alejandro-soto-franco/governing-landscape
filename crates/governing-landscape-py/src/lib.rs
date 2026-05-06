//! PyO3 bindings for the `governing-landscape` Rust crate.
//!
//! Surface (M1):
//!   - `__version__`
//!   - `geometric_features(means, opacities, colours, psi, n_instances) -> ndarray (n, 13)`
//!
//! M2 will add the typed-hypergraph PyClass surface and the constraint
//! projection operator.

use governing_landscape::{AlignmentMap, Splat3D, compute_geometric_features};
use ndarray::Array2;
use numpy::{IntoPyArray, PyArray2, PyReadonlyArray1, PyReadonlyArray2};
use pyo3::Bound;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(geometric_features, m)?)?;
    Ok(())
}

/// Per-instance geometric features (paper §3.5).
///
/// Args:
///     means       : (N, 3) float32, per-Gaussian means
///     opacities   : (N,)   float32, per-Gaussian opacities in [0, 1]
///     colours     : (N, 3) float32, per-Gaussian RGB colours
///     psi         : (N,)   uint32,  instance-assignment ψ : [N] → [n]
///     n_instances : int,            number of distinct instances n
///
/// Returns:
///     (n_instances, 13) float32 array. Each row is
///     `[μ̄_x, μ̄_y, μ̄_z, M_11, M_21, M_31, M_22, M_32, M_33, v, c̄_R, c̄_G, c̄_B]`.
#[pyfunction]
fn geometric_features<'py>(
    py: Python<'py>,
    means: PyReadonlyArray2<'py, f32>,
    opacities: PyReadonlyArray1<'py, f32>,
    colours: PyReadonlyArray2<'py, f32>,
    psi: PyReadonlyArray1<'py, u32>,
    n_instances: u32,
) -> PyResult<Bound<'py, PyArray2<f32>>> {
    let means_v = means.as_array();
    let alpha_v = opacities.as_array();
    let colour_v = colours.as_array();
    let psi_v = psi.as_array();

    let n = alpha_v.len();
    if means_v.shape() != [n, 3] {
        return Err(PyValueError::new_err(format!(
            "means must have shape (N, 3); got {:?}",
            means_v.shape()
        )));
    }
    if colour_v.shape() != [n, 3] {
        return Err(PyValueError::new_err(format!(
            "colours must have shape (N, 3); got {:?}",
            colour_v.shape()
        )));
    }
    if psi_v.len() != n {
        return Err(PyValueError::new_err(format!(
            "psi must have length N = {}; got {}",
            n,
            psi_v.len()
        )));
    }

    let splat = Splat3D {
        means: (0..n)
            .map(|i| [means_v[[i, 0]], means_v[[i, 1]], means_v[[i, 2]]])
            .collect(),
        opacities: alpha_v.to_vec(),
        colours: (0..n)
            .map(|i| [colour_v[[i, 0]], colour_v[[i, 1]], colour_v[[i, 2]]])
            .collect(),
    };
    splat
        .validate()
        .map_err(|e| PyValueError::new_err(e.to_string()))?;

    let align = AlignmentMap::new(psi_v.to_vec(), n_instances)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;

    let features = compute_geometric_features(&splat, &align);
    let mut out = Array2::<f32>::zeros((features.len(), 13));
    for (j, f) in features.iter().enumerate() {
        let row = f.flatten();
        for (k, &v) in row.iter().enumerate() {
            out[[j, k]] = v;
        }
    }
    Ok(out.into_pyarray(py))
}
