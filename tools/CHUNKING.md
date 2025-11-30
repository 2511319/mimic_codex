# CHUNKING RULES

Scope: Used by `tools/index_repo.py` for building embeddings.

- Sources: only files under `git ls-files`.
- Exclude defaults:
  - `deploy/**`, `observability/**`, `qa/**`
  - `**/__pycache__/**`, `**/node_modules/**`
  - build/CI artifacts

Chunking strategy:
- `.py`, `.ts`, `.tsx`: AST-aware chunking by top-level classes/functions where possible.
  - Python: `ast` to locate `ClassDef`/`FunctionDef`; include decorators and docstrings.
  - TypeScript/TSX: heuristic regex for `class`/`function`/`export function`/`export class`.
- Fallback: fixed-size window of 120 lines per chunk.

Embeddings:
- Code: `text-embedding-3-large`, `dimensions=1024`
- Docs: `text-embedding-3-small`, `dimensions=1024`

Notes:
- One chunk → one embedding request (to match operational guidance).
- Ensure CRLF/LF normalized before hashing.

