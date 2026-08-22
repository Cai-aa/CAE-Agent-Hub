# Contribute

Overall guidance on contributing to a PyAnsys library appears in the
[Contributing] topic in the *PyAnsys developer's guide*. Ensure that you
are thoroughly familiar with this guide before attempting to contribute to
{project-name}.

[Contributing]: https://dev.docs.pyansys.com/how-to/contributing.html

<!-- Begin content specific to your library here. -->
# Contribute

Overall guidance on contributing to a PyAnsys library appears in the
[Contributing] topic in the *PyAnsys developer's guide*. Ensure that you
are thoroughly familiar with this guide before attempting to contribute to
PyCFX MCP project.

The following contribution information is specific to PyCFX MCP.

[Contributing]: https://dev.docs.pyansys.com/how-to/contributing.html

## Development Setup

Use Python 3.12 or later.

```powershell
git clone https://github.com/ansys/pycfx-mcp.git
cd pycfx-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,doc]"
```

On Linux or macOS, activate the environment with:

```bash
source .venv/bin/activate
```

## Before you open a pull request

- **Lint:** `ruff check src tests`
- **Test:** `pytest -q`
- Keep changes focused and add a test for any bug fix or new behavior.
- Update `CHANGELOG.md` under the `Unreleased` heading.
- Do not commit secrets. `.env` is git-ignored; never add real keys to
  `.env.example`.

## Coding conventions

- Target Python 3.12+ and keep the package import-light (heavy/optional
  dependencies stay behind extras).
- The dependency direction is one-way: this package never imports a
  higher-level consumer.
- All outbound HTTP must verify TLS by default. Use
  `ansys.cfx.mcp.common.llm_wire.resolve_tls_verify()` rather than
  passing `verify=False`.

## Reporting security issues

Please follow [SECURITY.md](SECURITY.md). Do not file public issues for
vulnerabilities.

## License

By contributing, you agree that your contributions are licensed under the
project's Apache-2.0 license.
