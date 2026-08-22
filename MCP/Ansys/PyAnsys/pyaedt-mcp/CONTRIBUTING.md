# Contribute

Overall guidance on contributing to a PyAnsys library appears in the
[Contributing] topic in the *PyAnsys developer's guide*. Ensure that you
are thoroughly familiar with this guide before attempting to contribute to
PyAEDT MCP.

[Contributing]: https://dev.docs.pyansys.com/how-to/contributing.html

<!-- Begin content specific to your library here. -->

The following contribution information is specific to PyAEDT MCP.

## Add a new tool

PyAEDT MCP uses connection-aware tool visibility: tools that need a live
AEDT session are hidden until `launch_aedt` or `connect_to_aedt` succeeds.
This is enforced via tool **tags**.

When you add a new `@app.tool(...)` to `src/ansys/aedt/mcp/tools.py`:

- **Default case: The tool needs an AEDT connection.** Tag it with
  `REQUIRES_AEDT_TAG` (defined at the top of `tools.py`):

  ```python
  @app.tool(tags={REQUIRES_AEDT_TAG})
  def my_new_tool(ctx: Context, ...) -> str:
      ...
  ```

  No further action is required. PyAEDT MCP disables it until a session
  exists, then `enable_components(tags={REQUIRES_AEDT_TAG})` unlocks it.

- **Special case: The tool is genuinely usable BEFORE any AEDT session**
  (such as by an installation check or log reader). Do NOT add the tag. Add
  the tool's name to the `ALWAYS_AVAILABLE_TOOLS` allowlist in
  `tests/test_tools.py::TestRequiresAEDTVisibility::test_no_tool_surface_drift`.

The `test_no_tool_surface_drift` test fails if a new tool is neither
tagged nor on the allowlist. This is intentional. It forces every
contributor to make an explicit decision about pre-connection visibility.
