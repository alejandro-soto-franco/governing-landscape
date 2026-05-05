# Governing Generative Landscape Design

**Governing Generative Landscape Design: A Formal Mathematical Framework for 4D Gaussian Splatting and Semantic Hypergraph Integration in Indigenous Heritage Reconstruction**

Alejandro Soto Franco (Holonomy Securities) · Hamza Woodson (Jonathan Payne Lab, Stanford Doerr School of Sustainability)

---

## What this is

A mathematics white paper formalising a layered framework for governance-aware generative reconstruction of High Atlas heritage landscapes damaged by the September 2023 Al-Haouz earthquake, together with a Rust + Python implementation of the coupled data approach.

The framework couples two primary representations:

1. **4D Gaussian Splatting** over three temporal keyframes (pre-earthquake, post-earthquake, proposed reconstruction), providing a geometrically faithful 3D model of the physical landscape.
2. **Typed Governance Hypergraph** encoding Amazigh land tenure, oral histories, collective governance rules (Agdal), and contested ownership claims as first-class mathematical objects.

The two layers are coupled via an instance alignment map and fused into a joint embedding that drives constrained diffusion in Gaussian parameter space.

## Repository layout

```
paper/                                     mathematics white paper (XeLaTeX + Biber)
  main.tex
  references.bib
  main.pdf
crates/
  governing-landscape/                     core Rust crate
    src/{graph,splat,align,fusion}.rs
  governing-landscape-py/                  PyO3 bindings (PyPI: governing-landscape)
    python/governing_landscape/
    src/lib.rs
    pyproject.toml
Cargo.toml                                 workspace root
rust-toolchain.toml                        pinned 1.85.1
```

## Key contributions (paper)

- Formal definition of the typed hypergraph with five vertex types and six hyperedge types
- **Proposition** (§4.5): conflict-preserving hyperedge representation is mathematically necessary, since collapsing contested claims expands the feasible set and admits governance-violating designs
- Correction of the flat weighted-sum constraint aggregation used in prior work, via co-functional hyperedge routing
- Community validation active-learning loop with formal hypergraph update operators
- Field data collection protocol for on-site deployment in Morocco

## Building the paper

Requires XeLaTeX, Biber, and the `PakType Naskh Basic` font (for inline Arabic terms).

```bash
cd paper
xelatex main && biber main && xelatex main && xelatex main
```

A compiled `paper/main.pdf` is included in the repository.

## Building the Rust + Python implementation

Rust core:

```bash
cargo build --release
cargo test
```

Python bindings (uv + maturin):

```bash
cd crates/governing-landscape-py
uv venv && source .venv/bin/activate
uv pip install maturin pytest numpy
maturin develop --release
pytest tests
```

## License

MIT, see `LICENSE`.
