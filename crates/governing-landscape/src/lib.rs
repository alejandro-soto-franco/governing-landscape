#![doc = include_str!("../README.md")]

pub mod align;
pub mod fusion;
pub mod graph;
pub mod splat;

pub use align::AlignmentMap;
pub use fusion::JointEmbedding;
pub use graph::{
    ActorKind, ActorVertex, BooleanFormula, ContestedStatus, Deontic, EdgeId, EdgeKind, EventKind,
    EventVertex, GraphError, Hyperedge, Hypergraph, InstanceId, Language, NarrativeSource,
    NarrativeVertex, ResidencyStatus, RuleVertex, StructuralVertex, Vertex, VertexId, VertexKind,
};
pub use splat::Splat4D;
