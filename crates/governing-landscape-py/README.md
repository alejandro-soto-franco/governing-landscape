# governing-landscape (Python)

PyO3 bindings for the `governing-landscape` Rust crate.

Build (uv + maturin):

```bash
uv venv
uv pip install maturin
maturin develop --release
```

Then:

```python
import governing_landscape as gl
print(gl.__version__)
```
