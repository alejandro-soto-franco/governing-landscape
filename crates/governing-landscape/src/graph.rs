//! Typed governance hypergraph (paper §4).
//!
//! Five vertex types and six hyperedge types; conflict-preserving by construction
//! per §4.5.

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum VertexType {
    Parcel,
    Household,
    Lineage,
    Resource,
    Ritual,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum HyperedgeType {
    Tenure,
    Agdal,
    Inheritance,
    Use,
    Conflict,
    Provenance,
}

#[derive(Debug, Default)]
pub struct Hypergraph {
    // TODO: vertex/hyperedge storage; conflict-preserving co-functional routing.
}
