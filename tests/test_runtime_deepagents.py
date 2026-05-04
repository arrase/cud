from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from unittest import mock

from cud.agent.runtime import AgentRuntime
from cud.config.scaffold import create_agent


class RuntimeDeepAgentsTests(unittest.TestCase):
    def test_runtime_passes_unbound_chat_model_to_deepagents(self) -> None:
        captured = {}

        class FakeBoundModel:
            pass

        class FakeChatOllama:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def bind_tools(self, tools):
                return FakeBoundModel()

        def fake_create_deep_agent(**kwargs):
            captured["model"] = kwargs["model"]
            if isinstance(kwargs["model"], FakeBoundModel):
                raise AssertionError("model was bound before create_deep_agent")
            return {"graph": True}

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CUD_HOME"] = tmp
            path = create_agent("marvin")
            
            with unittest.mock.patch("cud.agent.runtime.create_deep_agent", fake_create_deep_agent), \
                 unittest.mock.patch("cud.agent.runtime.ChatOllama", FakeChatOllama):
                runtime = AgentRuntime(path)
                self.assertEqual(runtime.graph, {"graph": True})
                self.assertIsInstance(captured["model"], FakeChatOllama)

if __name__ == "__main__":
    unittest.main()

