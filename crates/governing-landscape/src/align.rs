//! Instance alignment map ψ : [N] → [n] (paper §3.4 def:psi, §5.1).
//!
//! ψ assigns each Gaussian to a structural-instance index. Every instance
//! must receive at least one Gaussian (surjection). The inverse partition
//! `{G_{s_j}}_{j=1}^n` is materialised eagerly so per-instance feature
//! aggregation is O(N) total across all instances.

use thiserror::Error;

#[derive(Debug, Error, PartialEq)]
pub enum AlignmentError {
    #[error("instance {0} has no assigned Gaussians; psi is not surjective")]
    NotSurjective(u32),
    #[error("Gaussian {gauss_idx} assigns to instance {target} but only {n_instances} declared")]
    OutOfRange {
        gauss_idx: usize,
        target: u32,
        n_instances: u32,
    },
}

#[derive(Debug, Clone, Default)]
pub struct AlignmentMap {
    psi: Vec<u32>,
    inverse: Vec<Vec<u32>>,
}

impl AlignmentMap {
    pub fn new(psi: Vec<u32>, n_instances: u32) -> Result<Self, AlignmentError> {
        let mut inverse: Vec<Vec<u32>> = (0..n_instances).map(|_| Vec::new()).collect();
        for (k, &target) in psi.iter().enumerate() {
            if target >= n_instances {
                return Err(AlignmentError::OutOfRange {
                    gauss_idx: k,
                    target,
                    n_instances,
                });
            }
            inverse[target as usize].push(k as u32);
        }
        for (j, inv) in inverse.iter().enumerate() {
            if inv.is_empty() {
                return Err(AlignmentError::NotSurjective(j as u32));
            }
        }
        Ok(Self { psi, inverse })
    }

    pub fn psi(&self, k: usize) -> u32 {
        self.psi[k]
    }

    pub fn instance_indices(&self, j: u32) -> &[u32] {
        &self.inverse[j as usize]
    }

    pub fn n_gaussians(&self) -> usize {
        self.psi.len()
    }

    pub fn n_instances(&self) -> usize {
        self.inverse.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn surjection_required() {
        assert!(matches!(
            AlignmentMap::new(vec![0, 0, 0], 2),
            Err(AlignmentError::NotSurjective(1))
        ));
    }

    #[test]
    fn out_of_range_target_is_rejected() {
        assert!(matches!(
            AlignmentMap::new(vec![0, 5], 2),
            Err(AlignmentError::OutOfRange { .. })
        ));
    }

    #[test]
    fn forward_and_inverse_are_consistent() {
        let psi = AlignmentMap::new(vec![0, 1, 0, 1, 2], 3).unwrap();
        assert_eq!(psi.n_gaussians(), 5);
        assert_eq!(psi.n_instances(), 3);
        assert_eq!(psi.psi(0), 0);
        assert_eq!(psi.psi(4), 2);
        assert_eq!(psi.instance_indices(0), &[0, 2]);
        assert_eq!(psi.instance_indices(1), &[1, 3]);
        assert_eq!(psi.instance_indices(2), &[4]);
    }
}
