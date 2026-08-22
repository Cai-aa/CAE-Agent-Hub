# Contribute

Overall guidance on contributing to a PyAnsys library appears in the
[Contributing] topic in the *PyAnsys developer's guide*. Ensure that you
are thoroughly familiar with this guide before attempting to contribute to
PyFluent MCP.

[Contributing]: https://dev.docs.pyansys.com/how-to/contributing.html

<!-- Begin content specific to your library here. -->
# Contribute

Overall guidance on contributing to a PyAnsys library appears in the
[Contributing] topic in the *PyAnsys developer's guide*. Ensure that you
are thoroughly familiar with this guide before attempting to contribute to
the PyFluent-MCP project.

The following contribution information is specific to PyFluent-MCP.

[Contributing]: https://dev.docs.pyansys.com/how-to/contributing.html

## Development setup

```bash
git clone https://github.com/ansys/pyfluent-mcp.git
cd pyfluent-mcp
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Unix: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[pyfluent,tests]"
python -m pip install ruff pre-commit
```

## Before you open a pull request

- **Lint:** `ruff check src tests`
- **Test:** `pytest -q`
- Keep changes focused and add a test for any bug fix or new behavior.
- Add a changelog fragment under `doc/changelog.d/` named
  `<pull-request-number>.<type>.md` (for example, `42.added.md` or
  `42.fixed.md`). This project uses [towncrier]; do not edit `CHANGELOG.md`
  directly. Valid types are `breaking`, `added`, `fixed`, `documentation`,
  `dependencies`, `maintenance`, `miscellaneous`, `test`, and `changed`.
- Do not commit secrets. `.env` is git-ignored; never add real keys to
  `.env.example`.

[towncrier]: https://towncrier.readthedocs.io/

## Coding conventions

- Target Python 3.12+ and keep the package import-light (heavy/optional
  dependencies stay behind extras).
- The dependency direction is one-way: this package never imports a
  higher-level consumer.
- All outbound HTTP must verify TLS by default. Use
  `ansys.fluent.mcp.common.network.resolve_tls_verify()` rather than
  passing `verify=False`.

## Reporting security issues

Please follow [SECURITY.md](SECURITY.md) — do not file public issues for
vulnerabilities.

## License

By contributing, you agree that your contributions are licensed under the
project's Apache-2.0 license.
