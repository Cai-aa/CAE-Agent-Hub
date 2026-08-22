# AGENTS.md

Quick reference for AI coding agents working in this repository. Full developer
guide lives at `doc/source/getting_started/develop_pylumerical_mcp.rst`.

## Always run pre-commit before declaring work done

This repo has quality gates that **must** pass: `ruff check`, `ruff format`,
`mypy`, `bandit`, license headers, etc. Pytest alone is not enough — `ruff
format` and `mypy` routinely catch issues the test suite cannot.

After **any** code change (source or tests), run:

```bash
pre-commit run --all-files
```

If a hook reformats files (ruff-format) or reports errors (mypy), fix them and
re-run until every hook reports `Passed`. Only then run the test suite:

```bash
pytest -m "not integration"   # fast unit tests, no Lumerical install needed
pytest -m integration         # only if Lumerical + license are available
```

## Project layout (essentials)

- `src/ansys/lumerical/mcp/` — server, tools, persistent-session subclass
- `src/ansys/lumerical/mcp/_subprocess_helpers.py` — code seeded into the
  `python -u -i` subprocess; never import it in the parent process (would
  trigger `matplotlib.use("Agg")` and the `ansys.lumerical.core` probe in the
  wrong place). Tests are the documented exception.
- `tests/` — unit tests use mocks; integration tests are marked
  `@pytest.mark.integration` and require a real Lumerical install.

## Conventions to preserve

- Tools return **JSON strings** built via `envelope_success`/`envelope_failure`
  in `session_helpers.py`. Do not invent ad-hoc shapes.

## Commit / PR etiquette

- Never commit unless the user explicitly asks.
- Never modify `.git/config` or use `--no-verify`.
- Use Conventional Commit prefixes (`fix:`, `feat:`, `chore:`, `docs:`...).
