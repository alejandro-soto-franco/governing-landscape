#![doc = include_str!("../README.md")]

pub mod align;
pub mod fusion;
pub mod graph;
pub mod splat;

pub use align::AlignmentMap;
pub use fusion::JointEmbedding;
pub use graph::{HyperedgeType, Hypergraph, VertexType};
pub use splat::Splat4D;
