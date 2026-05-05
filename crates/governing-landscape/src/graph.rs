//! Typed governance hypergraph (paper §4).
//!
//! The vertex set partitions into five typed subsets,
//! `V = Str ∪ Act ∪ Nar ∪ Rul ∪ Evt`, and edges are drawn from six types in
//! `𝒯_e = {owns, gov, test, cofunc, cont, temp}`.
//! Constructors enforce the cardinality and type-composition constraints
//! from §4.2; [`Hypergraph::validate`] additionally enforces the global
//! invariants from §4.5 (conflict-pair coverage) and §4.6
//! (governance consistency, structural completeness).

use std::collections::{BTreeMap, BTreeSet};
use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Ord, PartialOrd)]
pub struct VertexId(pub u32);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Ord, PartialOrd)]
pub struct EdgeId(pub u32);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Ord, PartialOrd)]
pub struct InstanceId(pub u32);

// ── vertex types ────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum VertexKind {
    Str,
    Act,
    Nar,
    Rul,
    Evt,
}

#[derive(Debug, Clone)]
pub enum Vertex {
    Structural(StructuralVertex),
    Actor(ActorVertex),
    Narrative(NarrativeVertex),
    Rule(RuleVertex),
    Event(EventVertex),
}

impl Vertex {
    pub fn kind(&self) -> VertexKind {
        match self {
            Vertex::Structural(_) => VertexKind::Str,
            Vertex::Actor(_) => VertexKind::Act,
            Vertex::Narrative(_) => VertexKind::Nar,
            Vertex::Rule(_) => VertexKind::Rul,
            Vertex::Event(_) => VertexKind::Evt,
        }
    }
}

#[derive(Debug, Clone)]
pub struct StructuralVertex {
    pub instance: InstanceId,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActorKind {
    Individual,
    Tawmat,
    Household,
    Jmaa,
    Guild,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResidencyStatus {
    Resident,
    NonResident,
    Diaspora,
    Unknown,
}

#[derive(Debug, Clone)]
pub struct ActorVertex {
    pub actor_kind: ActorKind,
    pub lineage_depth: u32,
    pub residency: ResidencyStatus,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Language {
    Tachelhit,
    Tamazight,
    Darija,
    French,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NarrativeSource {
    Oral,
    Cadastral,
    NgoSurvey,
    Photo,
    Heritage,
}

#[derive(Debug, Clone)]
pub struct NarrativeVertex {
    pub speaker: Option<VertexId>,
    pub recorded_at: i64,
    pub language: Language,
    pub source_kind: NarrativeSource,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Deontic {
    Permission,
    Prohibition,
    Obligation,
}

/// Boolean expression over hypergraph state. Only the trivial constants are
/// implemented in milestone 1; the typed-leaf grammar over attributes and
/// edge membership lands in milestone 2 alongside the constraint DSL.
#[derive(Debug, Clone)]
pub enum BooleanFormula {
    Always,
    Never,
}

impl BooleanFormula {
    pub fn evaluate(&self, _hg: &Hypergraph) -> bool {
        matches!(self, BooleanFormula::Always)
    }
}

#[derive(Debug, Clone)]
pub struct RuleVertex {
    pub deontic: Deontic,
    pub precondition: BooleanFormula,
    pub valid_from: Option<i64>,
    pub valid_to: Option<i64>,
    pub sensitivity: f32,
    pub authority: Vec<VertexId>,
}

impl RuleVertex {
    /// Whether `self` is active at unix-second `t` per §4.4.
    pub fn active_at(&self, t: i64, hg: &Hypergraph) -> bool {
        let lower_ok = self.valid_from.is_none_or(|from| t >= from);
        let upper_ok = self.valid_to.is_none_or(|to| t <= to);
        lower_ok && upper_ok && self.precondition.evaluate(hg)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EventKind {
    Construction,
    Damage,
    Inheritance,
    Earthquake,
    Reconstruction,
}

#[derive(Debug, Clone)]
pub struct EventVertex {
    pub at: i64,
    pub kind: EventKind,
    pub description: String,
}

// ── hyperedge types ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContestedStatus {
    Active,
    Mediation,
    Resolved,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EdgeKind {
    Owns,
    Gov,
    Testimony,
    Cofunc,
    Contested,
    Temporal,
}

#[derive(Debug, Clone)]
pub enum Hyperedge {
    Owns {
        members: BTreeSet<VertexId>,
    },
    Gov {
        members: BTreeSet<VertexId>,
    },
    Testimony {
        members: BTreeSet<VertexId>,
    },
    Cofunc {
        members: BTreeSet<VertexId>,
    },
    Contested {
        members: BTreeSet<VertexId>,
        status: ContestedStatus,
    },
    Temporal {
        members: BTreeSet<VertexId>,
        at: i64,
    },
}

impl Hyperedge {
    pub fn kind(&self) -> EdgeKind {
        match self {
            Hyperedge::Owns { .. } => EdgeKind::Owns,
            Hyperedge::Gov { .. } => EdgeKind::Gov,
            Hyperedge::Testimony { .. } => EdgeKind::Testimony,
            Hyperedge::Cofunc { .. } => EdgeKind::Cofunc,
            Hyperedge::Contested { .. } => EdgeKind::Contested,
            Hyperedge::Temporal { .. } => EdgeKind::Temporal,
        }
    }

    pub fn members(&self) -> &BTreeSet<VertexId> {
        match self {
            Hyperedge::Owns { members }
            | Hyperedge::Gov { members }
            | Hyperedge::Testimony { members }
            | Hyperedge::Cofunc { members }
            | Hyperedge::Contested { members, .. }
            | Hyperedge::Temporal { members, .. } => members,
        }
    }
}

// ── errors ──────────────────────────────────────────────────────────────────

#[derive(Debug, Error)]
pub enum GraphError {
    #[error("vertex {0:?} not found")]
    VertexNotFound(VertexId),
    #[error("edge {0:?} not found")]
    EdgeNotFound(EdgeId),
    #[error("edge violates type constraint: {0}")]
    EdgeTypeViolation(String),
    #[error("rule sensitivity must be in [0, 1]; got {0}")]
    InvalidSensitivity(f32),
    #[error(
        "conflict pair over structure {structure:?} ({e1:?}, {e2:?}) not covered by a Contested edge"
    )]
    UncoveredConflictPair {
        structure: VertexId,
        e1: EdgeId,
        e2: EdgeId,
    },
}

// ── hypergraph ──────────────────────────────────────────────────────────────

#[derive(Debug, Default, Clone)]
pub struct Hypergraph {
    vertices: BTreeMap<VertexId, Vertex>,
    edges: BTreeMap<EdgeId, Hyperedge>,
    next_vid: u32,
    next_eid: u32,
}

impl Hypergraph {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn add_vertex(&mut self, v: Vertex) -> Result<VertexId, GraphError> {
        if let Vertex::Rule(r) = &v {
            if !(0.0..=1.0).contains(&r.sensitivity) {
                return Err(GraphError::InvalidSensitivity(r.sensitivity));
            }
        }
        let id = VertexId(self.next_vid);
        self.next_vid += 1;
        self.vertices.insert(id, v);
        Ok(id)
    }

    pub fn add_edge(&mut self, e: Hyperedge) -> Result<EdgeId, GraphError> {
        self.check_edge_invariants(&e)?;
        let id = EdgeId(self.next_eid);
        self.next_eid += 1;
        self.edges.insert(id, e);
        Ok(id)
    }

    pub fn vertex(&self, id: VertexId) -> Option<&Vertex> {
        self.vertices.get(&id)
    }

    pub fn edge(&self, id: EdgeId) -> Option<&Hyperedge> {
        self.edges.get(&id)
    }

    pub fn vertices(&self) -> impl Iterator<Item = (&VertexId, &Vertex)> {
        self.vertices.iter()
    }

    pub fn edges(&self) -> impl Iterator<Item = (&EdgeId, &Hyperedge)> {
        self.edges.iter()
    }

    pub fn n_vertices(&self) -> usize {
        self.vertices.len()
    }

    pub fn n_edges(&self) -> usize {
        self.edges.len()
    }

    /// Iterator over structural-vertex IDs.
    pub fn structures(&self) -> impl Iterator<Item = VertexId> + '_ {
        self.vertices
            .iter()
            .filter_map(|(id, v)| matches!(v, Vertex::Structural(_)).then_some(*id))
    }

    /// Governance edges incident to `s`, mirroring the row `B^gov[s, :]` from §4.3.
    /// Returns an error if `s` is not a structural vertex.
    pub fn gov_row(&self, s: VertexId) -> Result<Vec<EdgeId>, GraphError> {
        match self.vertex(s) {
            Some(Vertex::Structural(_)) => {}
            Some(_) => {
                return Err(GraphError::EdgeTypeViolation(format!(
                    "{s:?} is not a Structural vertex"
                )));
            }
            None => return Err(GraphError::VertexNotFound(s)),
        }
        Ok(self
            .edges
            .iter()
            .filter_map(|(eid, e)| {
                matches!(e, Hyperedge::Gov { members } if members.contains(&s)).then_some(*eid)
            })
            .collect())
    }

    /// §4.6: every Str vertex is incident to ≥1 Owns and ≥1 Testimony edge.
    pub fn structurally_complete(&self) -> bool {
        self.structures().all(|s| {
            let has_owns = self
                .edges
                .values()
                .any(|e| matches!(e, Hyperedge::Owns { members } if members.contains(&s)));
            let has_test = self
                .edges
                .values()
                .any(|e| matches!(e, Hyperedge::Testimony { members } if members.contains(&s)));
            has_owns && has_test
        })
    }

    /// All conflict pairs (§4.5 Definition): pairs of distinct Owns edges that
    /// share a structural vertex but have distinct actor sets. Each shared
    /// structure yields one tuple `(e1, e2, structure)`.
    pub fn conflict_pairs(&self) -> Vec<(EdgeId, EdgeId, VertexId)> {
        let owns: Vec<(EdgeId, &BTreeSet<VertexId>)> = self
            .edges
            .iter()
            .filter_map(|(eid, e)| match e {
                Hyperedge::Owns { members } => Some((*eid, members)),
                _ => None,
            })
            .collect();

        let mut out = Vec::new();
        for i in 0..owns.len() {
            for j in (i + 1)..owns.len() {
                let (e1, m1) = owns[i];
                let (e2, m2) = owns[j];
                let actors1 = self.actors_in(m1);
                let actors2 = self.actors_in(m2);
                if actors1 == actors2 {
                    continue;
                }
                for v in m1.intersection(m2) {
                    if matches!(self.vertex(*v), Some(Vertex::Structural(_))) {
                        out.push((e1, e2, *v));
                    }
                }
            }
        }
        out
    }

    /// Whether every conflict pair is covered by a Contested edge that
    /// contains the disputed structure plus the union of disputing actors.
    pub fn conflict_pairs_covered(&self) -> bool {
        self.first_uncovered_conflict_pair().is_none()
    }

    fn first_uncovered_conflict_pair(&self) -> Option<(EdgeId, EdgeId, VertexId)> {
        for (e1, e2, structure) in self.conflict_pairs() {
            let claimants: BTreeSet<VertexId> = self
                .edge(e1)
                .map(|e| self.actors_in(e.members()))
                .unwrap_or_default()
                .union(
                    &self
                        .edge(e2)
                        .map(|e| self.actors_in(e.members()))
                        .unwrap_or_default(),
                )
                .copied()
                .collect();

            let covered = self.edges.values().any(|e| match e {
                Hyperedge::Contested { members, .. } => {
                    members.contains(&structure) && claimants.iter().all(|a| members.contains(a))
                }
                _ => false,
            });
            if !covered {
                return Some((e1, e2, structure));
            }
        }
        None
    }

    /// Run all global invariants (§4.5, §4.6). Returns the first error found.
    pub fn validate(&self) -> Result<(), GraphError> {
        for e in self.edges.values() {
            self.check_edge_invariants(e)?;
        }
        if let Some((e1, e2, structure)) = self.first_uncovered_conflict_pair() {
            return Err(GraphError::UncoveredConflictPair { structure, e1, e2 });
        }
        Ok(())
    }

    fn actors_in(&self, members: &BTreeSet<VertexId>) -> BTreeSet<VertexId> {
        members
            .iter()
            .filter(|v| matches!(self.vertex(**v), Some(Vertex::Actor(_))))
            .copied()
            .collect()
    }

    fn check_edge_invariants(&self, e: &Hyperedge) -> Result<(), GraphError> {
        for v in e.members() {
            if !self.vertices.contains_key(v) {
                return Err(GraphError::VertexNotFound(*v));
            }
        }
        let kind_of = |v: VertexId| self.vertex(v).map(Vertex::kind);
        let count_kind = |members: &BTreeSet<VertexId>, k: VertexKind| -> usize {
            members.iter().filter(|v| kind_of(**v) == Some(k)).count()
        };
        let any_kind = |members: &BTreeSet<VertexId>, k: VertexKind| -> bool {
            members.iter().any(|v| kind_of(*v) == Some(k))
        };

        match e {
            Hyperedge::Owns { members } => {
                if !any_kind(members, VertexKind::Act) || !any_kind(members, VertexKind::Str) {
                    return Err(GraphError::EdgeTypeViolation(
                        "Owns edge must contain ≥1 Actor and ≥1 Structural vertex".into(),
                    ));
                }
            }
            Hyperedge::Gov { members } => {
                if count_kind(members, VertexKind::Rul) != 1 {
                    return Err(GraphError::EdgeTypeViolation(
                        "Gov edge must contain exactly one Rule vertex (§4.4)".into(),
                    ));
                }
                if !any_kind(members, VertexKind::Str) {
                    return Err(GraphError::EdgeTypeViolation(
                        "Gov edge must contain ≥1 Structural vertex".into(),
                    ));
                }
            }
            Hyperedge::Testimony { members } => {
                if !any_kind(members, VertexKind::Nar) {
                    return Err(GraphError::EdgeTypeViolation(
                        "Testimony edge must contain ≥1 Narrative vertex".into(),
                    ));
                }
            }
            Hyperedge::Cofunc { members } => {
                if members.len() < 2 || members.iter().any(|v| kind_of(*v) != Some(VertexKind::Str))
                {
                    return Err(GraphError::EdgeTypeViolation(
                        "Cofunc edge must have ≥2 members, all Structural".into(),
                    ));
                }
            }
            Hyperedge::Contested { members, .. } => {
                if !any_kind(members, VertexKind::Str) || count_kind(members, VertexKind::Act) < 2 {
                    return Err(GraphError::EdgeTypeViolation(
                        "Contested edge must contain ≥1 Structural and ≥2 Actor vertices".into(),
                    ));
                }
            }
            Hyperedge::Temporal { members, .. } => {
                if !any_kind(members, VertexKind::Evt) {
                    return Err(GraphError::EdgeTypeViolation(
                        "Temporal edge must contain ≥1 Event vertex".into(),
                    ));
                }
                if members
                    .iter()
                    .any(|v| !matches!(kind_of(*v), Some(VertexKind::Evt) | Some(VertexKind::Str)))
                {
                    return Err(GraphError::EdgeTypeViolation(
                        "Temporal edge members must be Event or Structural vertices".into(),
                    ));
                }
            }
        }
        Ok(())
    }
}

// ── tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn structural() -> Vertex {
        Vertex::Structural(StructuralVertex {
            instance: InstanceId(0),
        })
    }
    fn actor() -> Vertex {
        Vertex::Actor(ActorVertex {
            actor_kind: ActorKind::Individual,
            lineage_depth: 1,
            residency: ResidencyStatus::Resident,
        })
    }
    fn narrative() -> Vertex {
        Vertex::Narrative(NarrativeVertex {
            speaker: None,
            recorded_at: 0,
            language: Language::Tachelhit,
            source_kind: NarrativeSource::Oral,
        })
    }
    fn rule(deontic: Deontic, sigma: f32) -> Vertex {
        Vertex::Rule(RuleVertex {
            deontic,
            precondition: BooleanFormula::Always,
            valid_from: None,
            valid_to: None,
            sensitivity: sigma,
            authority: Vec::new(),
        })
    }
    fn event() -> Vertex {
        Vertex::Event(EventVertex {
            at: 0,
            kind: EventKind::Earthquake,
            description: String::new(),
        })
    }
    fn members(vs: &[VertexId]) -> BTreeSet<VertexId> {
        vs.iter().copied().collect()
    }

    #[test]
    fn rule_sensitivity_must_be_in_unit_interval() {
        let mut hg = Hypergraph::new();
        assert!(matches!(
            hg.add_vertex(rule(Deontic::Prohibition, 1.5)),
            Err(GraphError::InvalidSensitivity(_))
        ));
        assert!(hg.add_vertex(rule(Deontic::Prohibition, 0.5)).is_ok());
    }

    #[test]
    fn owns_requires_actor_and_struct() {
        let mut hg = Hypergraph::new();
        let s = hg.add_vertex(structural()).unwrap();
        let a = hg.add_vertex(actor()).unwrap();
        assert!(matches!(
            hg.add_edge(Hyperedge::Owns {
                members: members(&[s])
            }),
            Err(GraphError::EdgeTypeViolation(_))
        ));
        assert!(matches!(
            hg.add_edge(Hyperedge::Owns {
                members: members(&[a])
            }),
            Err(GraphError::EdgeTypeViolation(_))
        ));
        assert!(
            hg.add_edge(Hyperedge::Owns {
                members: members(&[s, a])
            })
            .is_ok()
        );
    }

    #[test]
    fn gov_requires_exactly_one_rule_and_a_struct() {
        let mut hg = Hypergraph::new();
        let s = hg.add_vertex(structural()).unwrap();
        let r1 = hg.add_vertex(rule(Deontic::Prohibition, 0.5)).unwrap();
        let r2 = hg.add_vertex(rule(Deontic::Permission, 0.2)).unwrap();
        assert!(matches!(
            hg.add_edge(Hyperedge::Gov {
                members: members(&[r1])
            }),
            Err(GraphError::EdgeTypeViolation(_))
        ));
        assert!(matches!(
            hg.add_edge(Hyperedge::Gov {
                members: members(&[s, r1, r2])
            }),
            Err(GraphError::EdgeTypeViolation(_))
        ));
        assert!(
            hg.add_edge(Hyperedge::Gov {
                members: members(&[s, r1])
            })
            .is_ok()
        );
    }

    #[test]
    fn cofunc_must_be_all_structural_and_at_least_two() {
        let mut hg = Hypergraph::new();
        let s1 = hg.add_vertex(structural()).unwrap();
        let s2 = hg.add_vertex(structural()).unwrap();
        let a = hg.add_vertex(actor()).unwrap();
        assert!(matches!(
            hg.add_edge(Hyperedge::Cofunc {
                members: members(&[s1])
            }),
            Err(GraphError::EdgeTypeViolation(_))
        ));
        assert!(matches!(
            hg.add_edge(Hyperedge::Cofunc {
                members: members(&[s1, a])
            }),
            Err(GraphError::EdgeTypeViolation(_))
        ));
        assert!(
            hg.add_edge(Hyperedge::Cofunc {
                members: members(&[s1, s2])
            })
            .is_ok()
        );
    }

    #[test]
    fn temporal_must_have_event_and_only_evt_or_str() {
        let mut hg = Hypergraph::new();
        let s = hg.add_vertex(structural()).unwrap();
        let e = hg.add_vertex(event()).unwrap();
        let a = hg.add_vertex(actor()).unwrap();
        assert!(matches!(
            hg.add_edge(Hyperedge::Temporal {
                members: members(&[s]),
                at: 0
            }),
            Err(GraphError::EdgeTypeViolation(_))
        ));
        assert!(matches!(
            hg.add_edge(Hyperedge::Temporal {
                members: members(&[e, a]),
                at: 0
            }),
            Err(GraphError::EdgeTypeViolation(_))
        ));
        assert!(
            hg.add_edge(Hyperedge::Temporal {
                members: members(&[e, s]),
                at: 0
            })
            .is_ok()
        );
    }

    #[test]
    fn structurally_complete_detects_missing_testimony() {
        let mut hg = Hypergraph::new();
        let s = hg.add_vertex(structural()).unwrap();
        let a = hg.add_vertex(actor()).unwrap();
        hg.add_edge(Hyperedge::Owns {
            members: members(&[s, a]),
        })
        .unwrap();
        assert!(!hg.structurally_complete());
        let n = hg.add_vertex(narrative()).unwrap();
        hg.add_edge(Hyperedge::Testimony {
            members: members(&[s, n]),
        })
        .unwrap();
        assert!(hg.structurally_complete());
    }

    #[test]
    fn conflict_pair_detection() {
        let mut hg = Hypergraph::new();
        let s = hg.add_vertex(structural()).unwrap();
        let a1 = hg.add_vertex(actor()).unwrap();
        let a2 = hg.add_vertex(actor()).unwrap();
        let e1 = hg
            .add_edge(Hyperedge::Owns {
                members: members(&[s, a1]),
            })
            .unwrap();
        let e2 = hg
            .add_edge(Hyperedge::Owns {
                members: members(&[s, a2]),
            })
            .unwrap();
        assert_eq!(hg.conflict_pairs(), vec![(e1, e2, s)]);
    }

    #[test]
    fn validate_rejects_uncovered_conflict_pair() {
        let mut hg = Hypergraph::new();
        let s = hg.add_vertex(structural()).unwrap();
        let a1 = hg.add_vertex(actor()).unwrap();
        let a2 = hg.add_vertex(actor()).unwrap();
        hg.add_edge(Hyperedge::Owns {
            members: members(&[s, a1]),
        })
        .unwrap();
        hg.add_edge(Hyperedge::Owns {
            members: members(&[s, a2]),
        })
        .unwrap();
        assert!(matches!(
            hg.validate(),
            Err(GraphError::UncoveredConflictPair { .. })
        ));
    }

    #[test]
    fn validate_accepts_covered_conflict_pair() {
        let mut hg = Hypergraph::new();
        let s = hg.add_vertex(structural()).unwrap();
        let a1 = hg.add_vertex(actor()).unwrap();
        let a2 = hg.add_vertex(actor()).unwrap();
        hg.add_edge(Hyperedge::Owns {
            members: members(&[s, a1]),
        })
        .unwrap();
        hg.add_edge(Hyperedge::Owns {
            members: members(&[s, a2]),
        })
        .unwrap();
        hg.add_edge(Hyperedge::Contested {
            members: members(&[s, a1, a2]),
            status: ContestedStatus::Active,
        })
        .unwrap();
        assert!(hg.validate().is_ok());
    }

    #[test]
    fn gov_row_filters_by_structure_and_kind() {
        let mut hg = Hypergraph::new();
        let s1 = hg.add_vertex(structural()).unwrap();
        let s2 = hg.add_vertex(structural()).unwrap();
        let r1 = hg.add_vertex(rule(Deontic::Prohibition, 0.5)).unwrap();
        let r2 = hg.add_vertex(rule(Deontic::Obligation, 0.5)).unwrap();
        let g1 = hg
            .add_edge(Hyperedge::Gov {
                members: members(&[s1, r1]),
            })
            .unwrap();
        let _g2 = hg
            .add_edge(Hyperedge::Gov {
                members: members(&[s2, r2]),
            })
            .unwrap();
        assert_eq!(hg.gov_row(s1).unwrap(), vec![g1]);
        assert!(matches!(
            hg.gov_row(r1),
            Err(GraphError::EdgeTypeViolation(_))
        ));
    }

    #[test]
    fn rule_active_within_validity_interval() {
        let hg = Hypergraph::new();
        let r = RuleVertex {
            deontic: Deontic::Prohibition,
            precondition: BooleanFormula::Always,
            valid_from: Some(100),
            valid_to: Some(200),
            sensitivity: 1.0,
            authority: vec![],
        };
        assert!(!r.active_at(50, &hg));
        assert!(r.active_at(150, &hg));
        assert!(!r.active_at(250, &hg));
    }
}
