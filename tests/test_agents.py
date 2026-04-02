import re
from unittest.mock import MagicMock
import pytest
from backend.agents import extract_code, _chat_with_reasoning

# Mock OpenAI client and response structure
class DummyMessage:
    def __init__(self, content, reasoning=None):
        self.content = content
        if reasoning is not None:
            self.reasoning_content = reasoning

class DummyChoice:
    def __init__(self, message):
        self.message = message

class DummyResponse:
    def __init__(self, content, reasoning=None):
        self.choices = [DummyChoice(DummyMessage(content, reasoning))]

class DummyClient:
    def __init__(self):
        pass
    @property
    def chat(self):
        return self
    @property
    def completions(self):
        return self
    def create(self, model=None, messages=None, temperature=0.4):
        # return dummy response based on last user message
        user_msg = messages[-1]["content"]
        if "reasoning" in user_msg:
            return DummyResponse("test content", reasoning="step 1")
        return DummyResponse("test content")

# Test extract_code with fences
@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("```python\nprint(1)\n```", "print(1)") ,
        ("No fences", "No fences"),
        ("```\nprint(1)\n```", "print(1)"),
        ("```js\nconsole.log('hi');\n```", "console.log('hi');"),
    ],
)
def test_extract_code(input_text, expected):
    assert extract_code(input_text) == expected

# Test _chat_with_reasoning returns dict with content and optional reasoning
@pytest.mark.parametrize("has_reasoning", [True, False])
def test_chat_with_reasoning(has_reasoning):
    client = DummyClient()
    system = "system"
    user = f"message {'with reasoning' if has_reasoning else ''}"
    result = _chat_with_reasoning(client, "model", system, user)
    assert isinstance(result, dict)
    assert result["content"] == "test content"
    if has_reasoning:
        assert result.get("reasoning") == "step 1"
    else:
        assert "reasoning" not in result
