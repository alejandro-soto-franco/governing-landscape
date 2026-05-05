# governing-landscape

Core Rust crate for the coupled 4D Gaussian splatting and typed governance
hypergraph framework described in `paper/main.tex`.

Modules:

- `graph`  — typed governance hypergraph (5 vertex types, 6 hyperedge types)
- `splat`  — 4D Gaussian splatting over three temporal keyframes
- `align`  — instance alignment map between splat primitives and hypergraph vertices
- `fusion` — joint embedding for constrained diffusion in Gaussian parameter space
