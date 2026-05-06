//! Per-instance geometric features (paper §3.5 def:geom_feature).
//!
//! For each structural instance `s_j`, we compute
//! `g_{s_j} = [μ̄; vech(M); v; c̄] ∈ ℝ^13` with
//!
//! - `μ̄_{s_j} = Σ_k α_k μ_k / Σ_k α_k`           (opacity-weighted centroid)
//! - `M_{s_j} = Σ_k α_k (μ_k − μ̄)(μ_k − μ̄)ᵀ / Σ_k α_k` (second-moment matrix)
//! - `v_{s_j} = Σ_k α_k`                          (total opacity)
//! - `c̄_{s_j} = (1/|G_{s_j}|) Σ_k c_k`           (mean colour)
//!
//! Sums are over `k ∈ G_{s_j} = {k : ψ(k) = j}`. The flat-vector layout
//! is fixed at 13 dims (3 + 6 + 1 + 3) to match the `d_g = 13` default
//! dimensions in `docs/specs/2026-05-06-impl-spec-layers-2-4.md`.

use crate::align::AlignmentMap;
use crate::splat::Splat3D;
use nalgebra::{Matrix3, Vector3};
use rayon::prelude::*;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeomFeature {
    pub centroid: [f32; 3],
    /// `vech(M)` as `[M_11, M_21, M_31, M_22, M_32, M_33]`.
    pub second_moment: [f32; 6],
    pub total_opacity: f32,
    pub mean_colour: [f32; 3],
}

impl GeomFeature {
    /// 13-vector layout: `[μ̄; vech(M); v; c̄]`.
    pub fn flatten(&self) -> [f32; 13] {
        let mut out = [0.0_f32; 13];
        out[0..3].copy_from_slice(&self.centroid);
        out[3..9].copy_from_slice(&self.second_moment);
        out[9] = self.total_opacity;
        out[10..13].copy_from_slice(&self.mean_colour);
        out
    }
}

/// Compute one [`GeomFeature`] per instance, in instance-index order.
/// Parallelised over instances via rayon.
pub fn compute_geometric_features(splat: &Splat3D, align: &AlignmentMap) -> Vec<GeomFeature> {
    (0..align.n_instances() as u32)
        .into_par_iter()
        .map(|j| compute_one(splat, align.instance_indices(j)))
        .collect()
}

fn compute_one(splat: &Splat3D, idxs: &[u32]) -> GeomFeature {
    let n = idxs.len() as f32;
    let mut total_alpha = 0.0_f32;
    let mut weighted_mu = Vector3::<f32>::zeros();
    let mut total_colour = Vector3::<f32>::zeros();

    for &k in idxs {
        let i = k as usize;
        let alpha = splat.opacities[i];
        let mu = Vector3::from(splat.means[i]);
        let c = Vector3::from(splat.colours[i]);
        total_alpha += alpha;
        weighted_mu += alpha * mu;
        total_colour += c;
    }

    let centroid = if total_alpha > 0.0 {
        weighted_mu / total_alpha
    } else {
        Vector3::<f32>::zeros()
    };
    let mean_colour = if n > 0.0 {
        total_colour / n
    } else {
        Vector3::<f32>::zeros()
    };

    let mut sm = Matrix3::<f32>::zeros();
    if total_alpha > 0.0 {
        for &k in idxs {
            let i = k as usize;
            let alpha = splat.opacities[i];
            let mu = Vector3::from(splat.means[i]);
            let d = mu - centroid;
            sm += alpha * (d * d.transpose());
        }
        sm /= total_alpha;
    }

    GeomFeature {
        centroid: [centroid.x, centroid.y, centroid.z],
        second_moment: [
            sm[(0, 0)],
            sm[(1, 0)],
            sm[(2, 0)],
            sm[(1, 1)],
            sm[(2, 1)],
            sm[(2, 2)],
        ],
        total_opacity: total_alpha,
        mean_colour: [mean_colour.x, mean_colour.y, mean_colour.z],
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    fn splat_at(means: Vec<[f32; 3]>, alphas: Vec<f32>) -> Splat3D {
        let n = means.len();
        Splat3D {
            means,
            opacities: alphas,
            colours: vec![[0.5, 0.5, 0.5]; n],
        }
    }

    #[test]
    fn single_gaussian_centroid_equals_mean_and_moment_is_zero() {
        let splat = splat_at(vec![[1.0, 2.0, 3.0]], vec![0.7]);
        let psi = AlignmentMap::new(vec![0], 1).unwrap();
        let f = &compute_geometric_features(&splat, &psi)[0];
        assert_eq!(f.centroid, [1.0, 2.0, 3.0]);
        assert_eq!(f.second_moment, [0.0; 6]);
        assert_relative_eq!(f.total_opacity, 0.7);
    }

    #[test]
    fn opposing_pair_has_zero_centroid_and_unit_xx_moment() {
        let splat = splat_at(vec![[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]], vec![0.5, 0.5]);
        let psi = AlignmentMap::new(vec![0, 0], 1).unwrap();
        let f = &compute_geometric_features(&splat, &psi)[0];
        assert_relative_eq!(f.centroid[0], 0.0);
        assert_relative_eq!(f.centroid[1], 0.0);
        assert_relative_eq!(f.centroid[2], 0.0);
        assert_relative_eq!(f.second_moment[0], 1.0); // M_xx
        assert_relative_eq!(f.second_moment[3], 0.0); // M_yy
        assert_relative_eq!(f.second_moment[5], 0.0); // M_zz
        assert_relative_eq!(f.total_opacity, 1.0);
    }

    #[test]
    fn opacity_weighting_biases_centroid_toward_higher_alpha() {
        let splat = splat_at(vec![[10.0, 0.0, 0.0], [0.0, 0.0, 0.0]], vec![0.9, 0.1]);
        let psi = AlignmentMap::new(vec![0, 0], 1).unwrap();
        let f = &compute_geometric_features(&splat, &psi)[0];
        // (0.9 * 10 + 0.1 * 0) / 1.0 = 9.0
        assert_relative_eq!(f.centroid[0], 9.0);
    }

    #[test]
    fn instances_are_partitioned_independently() {
        let splat = splat_at(
            vec![
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [10.0, 0.0, 0.0],
                [11.0, 0.0, 0.0],
            ],
            vec![0.5, 0.5, 0.5, 0.5],
        );
        let psi = AlignmentMap::new(vec![0, 0, 1, 1], 2).unwrap();
        let f = compute_geometric_features(&splat, &psi);
        assert_eq!(f.len(), 2);
        assert_relative_eq!(f[0].centroid[0], 0.5);
        assert_relative_eq!(f[1].centroid[0], 10.5);
    }

    #[test]
    fn flatten_matches_documented_layout() {
        let g = GeomFeature {
            centroid: [1.0, 2.0, 3.0],
            second_moment: [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            total_opacity: 0.7,
            mean_colour: [0.1, 0.2, 0.3],
        };
        let v = g.flatten();
        assert_eq!(v.len(), 13);
        assert_eq!(&v[0..3], &[1.0, 2.0, 3.0]);
        assert_eq!(&v[3..9], &[10.0, 20.0, 30.0, 40.0, 50.0, 60.0]);
        assert_eq!(v[9], 0.7);
        assert_eq!(&v[10..13], &[0.1, 0.2, 0.3]);
    }

    #[test]
    fn equal_opacity_recovers_unweighted_mean() {
        let splat = splat_at(
            vec![[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [6.0, 0.0, 0.0]],
            vec![0.5, 0.5, 0.5],
        );
        let psi = AlignmentMap::new(vec![0, 0, 0], 1).unwrap();
        let f = &compute_geometric_features(&splat, &psi)[0];
        assert_relative_eq!(f.centroid[0], 3.0); // unweighted mean of {0, 3, 6}
    }
}
