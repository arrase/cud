from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cud.tools.filesystem import FileSystemTools


class FileSystemToolTests(unittest.TestCase):
    def test_outside_workspace_returns_tool_error_instead_of_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = FileSystemTools(Path(tmp))
            result = tools.ls("/home")
            self.assertIn("Tool error (PermissionError)", result)
            self.assertIn("outside workspace", result)

    def test_allow_traversal_permits_outside_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = FileSystemTools(Path(tmp), allow_traversal=True)
            result = tools.ls("/")
            self.assertNotIn("Tool error (PermissionError)", result)
            self.assertTrue(isinstance(result, str))
            # Just verify it doesn't fail with the permission error


if __name__ == "__main__":
    unittest.main()

