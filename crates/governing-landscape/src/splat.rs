//! Static 3D Gaussian splat representations.
//!
//! Per-Gaussian state needed for the §3.5 geometric-feature computation:
//! means, opacities, RGB colours. Full anisotropic covariances and SH
//! colour coefficients land in milestone 2 alongside the gsplat training
//! loop; M1 ships only what `def:geom_feature` consumes directly.

use thiserror::Error;

#[derive(Debug, Error, PartialEq)]
pub enum SplatError {
    #[error("inconsistent buffer lengths: means={means}, opacities={opacities}, colours={colours}")]
    InconsistentLengths {
        means: usize,
        opacities: usize,
        colours: usize,
    },
    #[error("opacity must be in [0, 1]; got {0} at index {1}")]
    InvalidOpacity(f32, usize),
    #[error("non-finite value at index {0}")]
    NonFinite(usize),
}

#[derive(Debug, Clone, Default)]
pub struct Splat3D {
    pub means: Vec<[f32; 3]>,
    pub opacities: Vec<f32>,
    pub colours: Vec<[f32; 3]>,
}

impl Splat3D {
    pub fn n(&self) -> usize {
        self.means.len()
    }

    pub fn is_empty(&self) -> bool {
        self.means.is_empty()
    }

    pub fn validate(&self) -> Result<(), SplatError> {
        if self.means.len() != self.opacities.len() || self.means.len() != self.colours.len() {
            return Err(SplatError::InconsistentLengths {
                means: self.means.len(),
                opacities: self.opacities.len(),
                colours: self.colours.len(),
            });
        }
        for (i, &a) in self.opacities.iter().enumerate() {
            if !a.is_finite() {
                return Err(SplatError::NonFinite(i));
            }
            if !(0.0..=1.0).contains(&a) {
                return Err(SplatError::InvalidOpacity(a, i));
            }
        }
        for (i, m) in self.means.iter().enumerate() {
            if m.iter().any(|x| !x.is_finite()) {
                return Err(SplatError::NonFinite(i));
            }
        }
        for (i, c) in self.colours.iter().enumerate() {
            if c.iter().any(|x| !x.is_finite()) {
                return Err(SplatError::NonFinite(i));
            }
        }
        Ok(())
    }
}

/// 4D temporal splat: a sequence of 3D keyframes with associated times.
/// Paper §3.3 uses three keyframes (pre-quake, post-quake, proposed).
#[derive(Debug, Clone, Default)]
pub struct Splat4D {
    pub keyframes: Vec<Splat3D>,
    pub times: Vec<f32>,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn one() -> Splat3D {
        Splat3D {
            means: vec![[0.0, 0.0, 0.0]],
            opacities: vec![0.5],
            colours: vec![[0.5, 0.5, 0.5]],
        }
    }

    #[test]
    fn validate_accepts_consistent() {
        assert!(one().validate().is_ok());
    }

    #[test]
    fn validate_rejects_inconsistent_lengths() {
        let s = Splat3D {
            means: vec![[0.0; 3]; 2],
            opacities: vec![0.5],
            colours: vec![[0.5; 3]; 2],
        };
        assert!(matches!(
            s.validate(),
            Err(SplatError::InconsistentLengths { .. })
        ));
    }

    #[test]
    fn validate_rejects_opacity_out_of_range() {
        let mut s = one();
        s.opacities[0] = 1.5;
        assert!(matches!(s.validate(), Err(SplatError::InvalidOpacity(..))));
    }

    #[test]
    fn validate_rejects_non_finite_mean() {
        let mut s = one();
        s.means[0][0] = f32::NAN;
        assert!(matches!(s.validate(), Err(SplatError::NonFinite(0))));
    }
}
