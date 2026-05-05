# Implementation spec, Layers II to IV

Date: 2026-05-06
Source: `paper/main.tex` at commit `bff9f71`
Scope: typed governance hypergraph, instance alignment, joint embedding, constrained generation, hard projection.

## 1. Scope and provenance

This spec turns the mathematics of paper sections 3.4, 3.5, 4, 5, and 6 into Rust + Python contracts. Layer I (4D Gaussian splatting) is wrapped from `gsplat` and not respecified here. Layer V (community validation loop) is in scope only insofar as the data structures it mutates are defined. Section 8 (field protocol) is out of scope for code.

Paper symbols mirrored verbatim where useful: $\mathcal{S}$ = Gaussian scene, $\mathcal{H}$ = hypergraph, $V = \mathrm{Str} \cup \mathrm{Act} \cup \mathrm{Nar} \cup \mathrm{Rul} \cup \mathrm{Evt}$, $\mathcal{T}_e = \{\mathrm{owns}, \mathrm{gov}, \mathrm{test}, \mathrm{cofunc}, \mathrm{cont}, \mathrm{temp}\}$, $\psi$ = instance alignment, $\mathbf{B}$ = incidence matrix, $\mathbf{Z}$ = joint-embedding matrix.

## 2. What the paper specifies precisely

These items have closed-form definitions in the paper. They are mechanical to implement.

### 2.1 Vertex schema (§4.1)

```rust
pub enum VertexKind { Str, Act, Nar, Rul, Evt }

pub struct StructuralVertex { id: VertexId, instance_id: InstanceId }

pub struct ActorVertex {
    id: VertexId,
    actor_kind: ActorKind,            // individual | tawmat | household | jmaa | guild
    lineage_depth: u32,
    residency: ResidencyStatus,
}

pub struct NarrativeVertex {
    id: VertexId,
    speaker: Option<ActorId>,
    recorded_at: Date,
    language: Language,                // Tachelhit | Tamazight | Darija | French
    source_kind: NarrativeSource,      // oral | cadastral | NGO | photo
}

pub struct RuleVertex {
    id: VertexId,
    deontic: Deontic,                  // Permission | Prohibition | Obligation
    precondition: BooleanFormula,      // over vertex attrs + edge membership
    valid_from: Option<Date>, valid_to: Option<Date>,
    sensitivity: f32,                  // sigma_r in [0, 1]
    authority: Vec<ActorId>,           // P_r
}

pub struct EventVertex { id: VertexId, when: Date, kind: EventKind, description: String }
```

`BooleanFormula` is an enum tree with leaves over typed attribute predicates. The grammar is small enough to fit on one page; Layer V annotation tools emit it.

### 2.2 Hyperedge schema (§4.2)

Six variants. Each edge is `BTreeSet<VertexId>` plus typed metadata:

```rust
pub enum Hyperedge {
    Owns      { id: EdgeId, members: Set<VertexId> },                 // owns ∩ Act ≠ ∅, ∩ Str ≠ ∅
    Gov       { id: EdgeId, members: Set<VertexId> },                 // gov ∩ Rul ≠ ∅, |∩ Rul| = 1 (§4.4)
    Testimony { id: EdgeId, members: Set<VertexId> },                 // test ∩ Nar ≠ ∅
    Cofunc    { id: EdgeId, members: Set<VertexId> },                 // ⊆ Str, |·| ≥ 2
    Contested { id: EdgeId, members: Set<VertexId>, status: ContestedStatus },
    Temporal  { id: EdgeId, members: Set<VertexId>, at: Date },       // members ⊆ Evt ∪ Str
}
```

Cardinality and type constraints from §4.2 are enforced in constructors and re-checked by `Hypergraph::validate()`.

### 2.3 Incidence and type-restricted decomposition (§4.3)

Type-restricted incidence $\mathbf{B}^\tau_{ve} = \mathbf{B}_{ve} \cdot \mathbf{1}[\phi_E(e) = \tau]$ with $\mathbf{B} = \sum_\tau \mathbf{B}^\tau$.

Storage: one CSR sparse matrix per edge type (`faer::sparse::SparseColMat<f32>`). The full incidence is recovered by lazy summation; in practice the typed HGNN consumes the per-type matrices directly.

Special case: `B_gov[s_j, :]` row is the input to $\mathcal{L}_{\mathrm{gov}}$ (eq §6.2). Provide `Hypergraph::gov_row(s_j) -> SparseRow` as a primitive.

### 2.4 Temporal activation (§4.4)

```rust
impl RuleVertex {
    pub fn active_at(&self, t: Date, hg: &Hypergraph) -> bool {
        in_interval(t, self.valid_from, self.valid_to) && hg.evaluate(&self.precondition)
    }
}
```

`hg.evaluate(&BooleanFormula)` is a pure function over the current vertex/edge state, side-effect free, used both at constraint-loss time and during community validation.

### 2.5 Conflict-preserving representation (§4.5)

Proposition 4.5 is a necessity result, not an algorithm. The implementation obligation it generates is one negative invariant:

> Never replace two distinct ownership hyperedges that share a structural vertex with a single ownership hyperedge during automated graph operations.

Concretely: the `Hypergraph::add_edge` and `Hypergraph::merge_edges` APIs reject any merge whose members trigger Definition 4.5.1 (conflict pair). Conflict pairs are instead surfaced as a `Contested` hyperedge with `status = active | mediation | resolved`. Resolution is human-only: the only way to remove a `Contested` edge is via a Layer V update operator with `actor ∈ authority(rule)` provenance.

Test obligation: a property-based test asserts that, for every hypergraph reachable through the API, no conflict pair lacks a covering `Contested` edge.

### 2.6 Soundness invariants (§4.6)

Two predicates, both pure functions on `Hypergraph`:

```rust
fn governance_consistent(hg: &Hypergraph, t: Date) -> bool;
fn structurally_complete(hg: &Hypergraph) -> bool;     // every Str vertex has ≥1 Owns and ≥1 Test edge
```

Generation is gated on `structurally_complete`. Active learning (Layer V) prioritises Str vertices that fail the predicate. `governance_consistent` is checked at $\tau_{\mathrm{rec}}$ before generation runs.

### 2.7 Instance alignment $\psi$ (§3.4, §5.1)

$\psi : [N] \to [n]$ is a surjection from Gaussian indices to structural-instance indices. Storage: a contiguous `Vec<u32>` of length $N$, plus a CSR-style inverse `Vec<Range<u32>>` of length $n$ for $G_{s_j}$ lookup. Construction is delegated to either SAM-via-projection (paper §3.4) or Gaussian Grouping (Ye et al. 2024); we wrap whichever is available in `gsplat` and keep $\psi$ as the data interface.

### 2.8 Geometric features (§3.5)

Per-instance $\mathbf{g}_{s_j} = [\bar{\boldsymbol{\mu}}; \mathrm{vech}(\mathbf{M}); v; \bar{\mathbf{c}}]$, opacity-weighted. Closed-form, $\mathcal{O}(N)$, parallel over instances via rayon. Tested against a NumPy reference on synthetic clouds.

### 2.9 Joint embedding (§5.3)

$\mathbf{z}_{s_j} = \mathrm{MLP}_\phi(\mathbf{W}_h \mathbf{h}_{s_j}^{(L)} \,\|\, \mathbf{W}_g \mathbf{g}_{s_j})$ with $\mathbf{W}_h \in \mathbb{R}^{d_z/2 \times d_h}$, $\mathbf{W}_g \in \mathbb{R}^{d_z/2 \times d_g}$, two-layer MLP. Default dims: $d_g = 13$ (3 + 6 + 1 + 3), $d_h = 64$, $d_z = 64$, MLP hidden 128, GELU. All trainable; lives in PyTorch, not Rust.

Damage-keyframe extension: $\mathbf{g}_{s_j}^{(t_1)}$ appends $d_{s_j}$ (mean displacement magnitude) and $\bar{\mathbf{D}}_{s_j} \in \mathbb{R}^3$ for a total $d_g^{(t_1)} = 17$.

### 2.10 Typed HGNN (eq:typed_hgnn, §2.5)

$$\mathbf{h}_v^{(\ell+1)} = \sigma\Bigl(\sum_{\tau \in \mathcal{T}_e} \mathbf{W}_\tau^{(\ell)}\,\rho_{2,\tau}\bigl(\{\mathbf{z}_e^{(\ell)} : v \in e,\, \phi_E(e)=\tau\}\bigr)\Bigr)$$

Default aggregator: AllSet (Chien et al. 2022) for both $\rho_1$ and $\rho_{2,\tau}$. Six per-type weight matrices per layer; two layers ($L = 2$). Implementation: PyTorch + torch-scatter. Rust side ships only the typed incidence; HGNN forward pass is Python.

### 2.11 Total loss (§6.2)

$$\mathcal{L}_{\mathrm{tot}} = \mathcal{L}_{\mathrm{rec}} + \lambda_1\,\mathcal{L}_{\mathrm{struct}} + \lambda_2\,\mathcal{L}_{\mathrm{gov}}$$

- $\mathcal{L}_{\mathrm{rec}}$: bidirectional Chamfer distance between Gaussian mean clouds, weighted by $w_j^{\mathrm{rec}}$. Implementation: PyTorch (autograd through Gaussian means; `pytorch3d.loss.chamfer_distance` or hand-rolled k-NN).
- $\mathcal{L}_{\mathrm{gov}}$: sum over active rules of $c_r$ (eq §6.2.3), case split on deontic modality. Squared positive part of the constraint function value.
- $\mathcal{L}_{\mathrm{struct}}$: three rough proxies $\ell_{\mathrm{floor}} + \ell_{\mathrm{clearance}} + \ell_{\mathrm{mass}}$ — see research gap §3.2.

### 2.12 Diffusion conditioning (§6.3)

Forward: standard DDPM (Ho et al. 2020) on flattened $\mathbf{x} = [\mathbf{x}_{s_1}; \ldots; \mathbf{x}_{s_n}]$. Reverse: $\epsilon_\theta(\mathbf{x}^{(\tau)}, \mathbf{Z}, \mathbf{D}, \tau)$ is a GNN with cross-attention to $\mathbf{Z}$ and $\mathbf{D}$, propagating along co-functional hyperedges. Conditioning interface specified; backbone choice is a research gap (§3.4).

### 2.13 Hard constraint projection (§6.4)

```rust
fn project_hard(x: &mut ParamVec, hard_rules: &[RuleVertex], hg: &Hypergraph);
```

For convex feasible sets $\mathcal{C}_r$: closed-form projection per rule. For non-convex: sequential projection heuristic over $\mathrm{Rul}_{\mathrm{hard}} = \{r : \tau_r = \mathrm{Prohibition} \land \sigma_r = 1\}$. Applied after every reverse diffusion step. Rust-side; CPU is fine (small subset of rules per scene). Tested with a fixed-point convergence check.

## 3. What the paper does NOT specify (research gaps)

These items have a signature in the paper but no construction. They block end-to-end runs and need design decisions before code commits.

### 3.1 Per-rule constraint function $f_r$

Paper signature: $f_r : \mathcal{S}'_{s_j} \to \mathbb{R}$, positive when configuration of $s_j$ violates a prohibition, negative when it fulfils an obligation.

Paper gives prose examples but no general schema. Two implementation styles to pick from:

- **A. Domain-specific language.** A small expression DSL over instance geometry primitives (centroid, principal axes, volume, intersection-with-region, distance-to-feature, line-of-sight). Each rule is annotated by a community session and compiled to a closure. Pros: extensible, auditable. Cons: every new rule type needs DSL primitives.
- **B. Learned constraint head.** A small neural network per rule type, trained from labelled (compliant, violating) example pairs. Pros: handles fuzzy cultural constraints. Cons: needs labelled data we will not have early; opaque to community auditors.

Recommendation: A for milestone 1. B is a research extension, not foundational. The initial DSL primitive set (closed-form, sub-differentiable, all exposed to PyTorch via the joint-embedding pipeline) is:

| Primitive                              | Signature                                              | Paper rule it expresses                              |
|----------------------------------------|--------------------------------------------------------|------------------------------------------------------|
| `REGION_CONTAINS(s_j, R)`              | $\mathbb{1}[\bar{\boldsymbol{\mu}}_{s_j} \in R]$       | Agdal grazing prohibition; no construction in zone   |
| `REGION_DISJOINT(s_j, R)`              | $\mathrm{dist}(\bar{\boldsymbol{\mu}}_{s_j}, R)$       | Sacred enclosure exclusion                           |
| `HEIGHT(s_j) <= h_max`                 | top eigenvalue of $\mathbf{M}_{s_j}$ along $\hat{z}$   | "no structure taller than the mosque"                |
| `HEIGHT(s_j) >= h_min`                 | same                                                   | habitable-clearance obligation                       |
| `DISTANCE(s_j, s_k) >= d_min`          | $\|\bar{\boldsymbol{\mu}}_{s_j} - \bar{\boldsymbol{\mu}}_{s_k}\|$ | parcel separation                          |
| `CONTACT(s_j, s_k, eps)`               | bounding-ellipsoid distance with tolerance             | granary-threshing-floor adjacency                    |
| `LOS(p, q, S_blocking)`                | min ray-ellipsoid penetration over $S_\mathrm{blocking}$ | view-corridor preservation                         |
| `PATH_PRESERVED(s_j, ref_path, eps)`   | Hausdorff distance, instance centre to reference path  | water channel alignment must not shift               |
| `FOOTPRINT_AREA(s_j) <= a_max`         | XY-projection of bounding ellipsoid                    | parcel-size cap                                      |

All return $\mathbb{R}_{\geq 0}$ (signed by deontic modality per eq §6.2.3) and are differentiable in the Gaussian parameters via the geometric-feature pipeline of §3.5. Polytopal regions $R$ are stored as half-space sets `Vec<HalfSpace>`; `dist(·, R)` is the standard convex projection. The DSL grammar is small (literals, primitives, `AND` / `OR` / `NOT`, comparisons) and serialised in TOML alongside each rule vertex for community auditability. Layer V annotation tools emit DSL strings; the Rust side parses, type-checks, and compiles them into closures at hypergraph-load time.

### 3.2 Structural feasibility components

$\ell_{\mathrm{floor}}$, $\ell_{\mathrm{clearance}}$, $\ell_{\mathrm{mass}}$ are described in prose. We need closed-form penalties. Proposed defaults:

- $\ell_{\mathrm{floor}}(s_j) = \sum_{k : \psi(k)=j} \mathrm{ReLU}(z_{\mathrm{terrain}}(\mu_{k,xy}) - \mu_{k,z})^2$
- $\ell_{\mathrm{clearance}}(s_j) = \mathrm{ReLU}(h_{\min} - \mathrm{height}(\mathbf{M}_{s_j}))^2$ for habitable instances
- $\ell_{\mathrm{mass}}(s_j) = \mathrm{ReLU}(\rho_{\max} - v_{s_j} / \mathrm{height}(\mathbf{M}_{s_j}))^2$

These are first-pass; the paper explicitly defers to future structural-FEM work.

### 3.3 Hard-constraint feasible-set parameterisation

Paper names "sacred enclosures that must not be built upon" and "water channels whose alignment must not be altered" but does not give the analytic form of $\mathcal{C}_r$ for either. Both reduce to convex-region exclusion / inclusion if regions are stored as polytopes; we choose polytopal half-space encoding for both, with the half-spaces lifted from community annotation.

### 3.4 Denoising-network architecture

Paper says "GNN backbone with cross-attention". Free parameters: number of layers, hidden dim, attention heads, message-passing operator, time-conditioning style (FiLM vs concat), parameter sharing across instances. Proposed default for milestone 2: 6-layer DiT-style transformer with hyperedge-routed attention (hyperedge tokens added to the sequence, gated by edge type).

### 3.5 Damage displacement field $\mathbf{D}$ (resolved)

§3.3 (Definition: Displacement field) gives $\mathbf{D}(g_k) = \boldsymbol{\mu}_k^{(t_1)} - \boldsymbol{\mu}_k^{(t_0)}$ after the SE(3) registration of eq §3.2 (Keyframe registration), which is one-sided Chamfer minimisation $\mathbf{T}^* = \arg\min_{\mathbf{T} \in \mathrm{SE}(3)} \sum_k \min_j \|\boldsymbol{\mu}_k^{(t_0)} - \mathbf{T}\boldsymbol{\mu}_j^{(t_1)}\|^2$.

Implementation: `governing-landscape::register::align_keyframes(splat_t0, splat_t1) -> SE3` then `displacement_field(splat_t0, splat_t1, T) -> Vec<Vector3<f32>>`. The nearest-neighbour matching needed for per-Gaussian $\mathbf{D}(g_k)$ is computed by FLANN on the post-aligned $t_1$ mean cloud. The paper notes this is asymmetric (rubble Gaussians in $t_1$ have no $t_0$ counterpart, collapsed regions in $t_0$ have no $t_1$ counterpart); this is handled by capping $\|\mathbf{D}(g_k)\|$ at a damage-threshold above which the Gaussian is flagged "lost" rather than displaced.

## 4. Rust / Python boundary

| Concern                                 | Rust                                  | Python                                  |
|-----------------------------------------|---------------------------------------|-----------------------------------------|
| Hypergraph types, validation, invariants | ✓                                     |                                         |
| Typed incidence (sparse matrices)        | ✓ (faer)                              |                                         |
| Conflict-preservation invariant tests    | ✓ (proptest)                          |                                         |
| Geometric feature aggregation            | ✓ (rayon)                             |                                         |
| Constraint function DSL evaluation       | ✓                                     |                                         |
| Hard-constraint projection               | ✓                                     |                                         |
| 4D Gaussian splatting                    |                                       | ✓ (gsplat wrapper)                      |
| Typed HGNN forward pass                  |                                       | ✓ (PyTorch + torch-scatter)             |
| Joint embedding MLP                      |                                       | ✓ (PyTorch)                             |
| Diffusion train + sample                 |                                       | ✓ (PyTorch)                             |
| Chamfer / structural / governance loss   |                                       | ✓ (autograd needed)                     |
| Rendering for community validation UI    |                                       | ✓ (gsplat)                              |
| Persistent store of $\mathcal{H}$        | ✓ (sqlite via rusqlite)               |                                         |

PyO3 surface (initial): `Hypergraph`, `RuleVertex`, `validate`, `gov_row`, `geom_features`, `project_hard`. Numpy interop via numpy 0.28.

## 5. Milestone 1 (target ~1 week, no rented compute)

Deliverable: a runnable demo that loads a sparse SfM cloud, builds a 5-vertex hypergraph by hand, computes per-instance geometric features in Rust, calls Python to optimise gsplat for 1k iters, and prints `validate()` + `structurally_complete()` results.

Steps:

1. Strip Hamza from `Cargo.toml` and `pyproject.toml` author lists. Mechanical.
2. Site selection. Audit Wikimedia + Maxar Open Data for one High Atlas village with both pre-Sept-2023 photos and post-quake imagery. Tafza, Moulay Brahim, and Imi N'Tala are candidates. Output: `data/sites/<site>/manifest.toml` (tracked) plus binaries (gitignored).
3. Read §3.3 (temporal keyframe structure) and resolve research gap §3.5.
4. Implement §2.1, §2.2 in `crates/governing-landscape/src/graph.rs` with `validate()`. Property-based tests for the conflict-pair invariant (§2.5).
5. Implement §2.3, §2.6, §2.7, §2.8 in Rust. Tests against a NumPy reference for §2.8.
6. Wire `governing-landscape-py` to gsplat: load sparse cloud, run 1k iters, dump a `.ply` of Gaussian means. Smoke test only, no 4D, no diffusion.
7. End-to-end demo script under `examples/m1_demo.py` that exercises the full chain on the chosen site.

Out of scope for milestone 1: HGNN training, joint embedding, diffusion, all loss components, hard projection, Layer V UI.

## 6. Open questions and decisions

| Item                                | Status                                                                |
|-------------------------------------|-----------------------------------------------------------------------|
| Site for milestone 1                | Imagery audit running; will recommend on completion                   |
| Constraint DSL primitives           | Resolved (§3.1, nine-primitive table)                                 |
| Persistence backend                 | Resolved: SQLite via rusqlite                                         |
| Compute for HGNN / diffusion        | Resolved: Hamza brokers Stanford resource when needed                 |
| Hamza in code metadata              | Resolved: removed from `Cargo.toml` and `pyproject.toml` (paper only) |
| License                             | Deferred                                                              |
| Hard-constraint feasible-set parameterisation | Polytopal half-spaces (§3.3); confirmed |
| Denoiser architecture (§3.4)        | Default DiT-style with hyperedge-routed attention; revisit at M2     |
