"""Exercise the MCP file tool without using a CAE session."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mcp_server


class FileToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_file_tool_works_without_bridge_connection(self):
        tool = getattr(mcp_server, "inspect_job_files", None)
        self.assertIsNotNone(tool, "local job-files MCP tool is not exposed")
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "Example.sta").write_text(" THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n")
            with patch.object(mcp_server, "_bridge_request", side_effect=AssertionError("must not use bridge")):
                result = await tool("Example", directory)
            self.assertEqual(result["state"], "completed")


if __name__ == "__main__":
    unittest.main()
