# tests/

Mirrors `src/`: one subpackage per context (`tests/registry/`, `tests/capture/`,
…) plus `tests/api/` and shared fixtures in `tests/conftest.py`.

- Unit tests for a context live under that context's folder and stay within its
  boundary.
- Tests that cross contexts (pipeline, event routing) go under `tests/integration/`.
- Run with `uv run pytest`.
