# Contribute

Overall guidance on contributing to a PyAnsys library appears in the
[Contributing] topic in the *PyAnsys developer's guide*. Ensure that you
are thoroughly familiar with this guide before attempting to contribute to
PyMechanical MCP.

[Contributing]: https://dev.docs.pyansys.com/how-to/contributing.html

<!-- Begin content specific to your library here. -->
# Contribute

Overall guidance on contributing to a PyAnsys library appears in the
[Contributing] topic in the *PyAnsys developer's guide*. Ensure that you
are thoroughly familiar with this guide before attempting to contribute to
the PyMechanical MCP project.

The following contribution information is specific to PyMechanical MCP.

[Contributing]: https://dev.docs.pyansys.com/how-to/contributing.html

## Adding a new tool

`pymechanical-mcp` uses connection-aware tool visibility: tools that need a
live Mechanical session are hidden until `launch_mechanical` or
`connect_to_mechanical` succeeds. This is enforced via tool **tags**.

When you add a new `@app.tool(...)` to `src/ansys/mechanical/mcp/tools.py`:

- **Default case - the tool needs a Mechanical connection.** Tag it with
  `REQUIRES_MECHANICAL_TAG` (defined at the top of `tools.py`):

  ```python
  @app.tool(tags={REQUIRES_MECHANICAL_TAG})
  def my_new_tool(ctx: Context, ...) -> str:
      ...
  ```

  The server disables it until a session exists, then unlocks it via
  `enable_components(tags={REQUIRES_MECHANICAL_TAG})`.

- **Special case: the tool is genuinely usable BEFORE any Mechanical
  session** (e.g. an installation check). Do NOT add the tag, and add the
  tool's name to the `ALWAYS_AVAILABLE_TOOLS` allowlist in
  `tests/test_tools.py::TestRequiresMechanicalVisibility::test_no_tool_surface_drift`.

The `test_no_tool_surface_drift` test will fail if a new tool is neither
tagged nor on the allowlist. This is intentional: it forces every
contributor to make an explicit decision about pre-connection visibility.
