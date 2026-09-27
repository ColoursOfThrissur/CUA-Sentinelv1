import os
import sys
import pytest
from pathlib import Path

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.router import IntentRouter
from agents.cua_agent import CUAAgent
from tools.web_search import WebSearchTool


def test_intent_router_classifies_desktop_file_creation():
    # Prompts that must route to CUA
    cua_prompts = [
        "can u create a new txt file in my Desktop",
        "create a file on my desktop",
        "make a new file called notes on desktop",
        "write a text file in my Desktop with content hello",
        "can u create a filew on desktop",
        "/desktop inspect active window",
    ]
    for prompt in cua_prompts:
        intent = IntentRouter.classify_intent(prompt)
        assert intent == "CUA", f"Failed to classify '{prompt}' as CUA (got {intent})"

    # Even if explicit_workflow='ENDPOINT' was passed from chat, it should resolve to CUA
    for prompt in cua_prompts:
        intent = IntentRouter.classify_intent(prompt, explicit_workflow="ENDPOINT")
        assert intent == "CUA", f"Failed to route '{prompt}' with explicit_workflow=ENDPOINT to CUA (got {intent})"


def test_cua_agent_extracts_file_intent():
    agent = CUAAgent.__new__(CUAAgent)
    
    fn, content = agent._extract_file_intent("can u create a new txt file in my Desktop")
    assert fn.endswith(".txt")
    assert "Desktop" in content

    fn2, content2 = agent._extract_file_intent("create a file named my_ideas on my desktop with content 'build ai tools'")
    assert fn2 == "my_ideas.txt"
    assert "build ai tools" in content2

    fn3, _ = agent._extract_file_intent("can u create a filew on desktop")
    assert fn3.endswith(".txt") or fn3.endswith(".md")


def test_web_search_news_intent_and_live_feed():
    tool = WebSearchTool()
    
    # News intent detection
    assert tool._has_news_intent("latest news on OpenAI") is True
    assert tool._has_news_intent("what is the news today") is True
    assert tool._has_news_intent("current updates on AI") is True
    assert tool._has_news_intent("python list comprehension tutorial") is False

    # Live news search returns structured entries with publication dates
    results = tool._search_google_news("OpenAI", max_results=3)
    assert len(results) > 0
    first = results[0]
    assert "url" in first
    assert "title" in first
    assert "Published:" in first["snippet"]
    assert first["engine"] == "Google-News-Live"


def test_web_search_news_does_not_return_wikipedia():
    tool = WebSearchTool()
    # When querying with news intent, Wikipedia should not be used
    results = tool.search_structured("latest news on technology", max_results=3)
    assert len(results) > 0
    for r in results:
        assert r["engine"] != "Wikipedia", f"News query should not return Wikipedia, got {r}"


def test_endpoint_agent_extracts_file_update_intent():
    from agents.endpoint_agent import EndpointAgent
    agent = EndpointAgent.__new__(EndpointAgent)

    # Multi-turn history reference
    history = [
        {"role": "user", "content": "can u create a new txt file in desktop"},
        {"role": "assistant", "content": "✅ Successfully created file `new_file.txt` on your Desktop at `C:\\Users\\Desktop\\new_file.txt`."},
    ]
    prompt = "in the new txt file u created above can u paste the todays gmail first 10 messages"
    target, ctype = agent._extract_file_update_intent(prompt, history)
    assert target == "new_file.txt"
    assert ctype == "GMAIL"

    # Explicit filename in prompt
    prompt2 = "can u paste the latest AI news into my_notes.md"
    target2, ctype2 = agent._extract_file_update_intent(prompt2, [])
    assert target2 == "my_notes.md"
    assert ctype2 == "WEB"


def test_desktop_file_write_overwrite_behavior(tmp_path, monkeypatch):
    from tools.desktop_tool import DesktopTool
    monkeypatch.setenv("SENTINEL_DESKTOP_DIR", str(tmp_path))
    tool = DesktopTool()

    # 1. First write succeeds
    res1 = tool.desktop_file_write("test_overwrite.txt", "Initial content")
    assert res1["status"] == "SUCCESS"
    assert (tmp_path / "test_overwrite.txt").read_text() == "Initial content"

    # 2. Second write without overwrite fails
    res2 = tool.desktop_file_write("test_overwrite.txt", "Second content", overwrite=False)
    assert res2["status"] == "FAILED"
    assert "already exists" in res2["error"]

    # 3. Third write with overwrite=True succeeds
    res3 = tool.desktop_file_write("test_overwrite.txt", "Updated content", overwrite=True)
    assert res3["status"] == "SUCCESS"
    assert (tmp_path / "test_overwrite.txt").read_text() == "Updated content"


def test_base_agent_lazy_handler_registration_and_none_config():
    from agents.base_agent import BaseAgent
    class ConcreteAgent(BaseAgent):
        async def run(self, claim): pass

    # Test None config does not throw AttributeError
    agent = ConcreteAgent(None, None, None)
    assert agent.config == {}
    assert agent.max_tool_calls_per_task == 50

    # Test lazy registration when map is empty
    BaseAgent._TOOL_HANDLERS.clear()
    assert len(BaseAgent._TOOL_HANDLERS) == 0
    handler = agent._resolve_tool_handler("web_search")
    assert handler is not None
    assert callable(handler)
    assert "search_emails" in BaseAgent._TOOL_HANDLERS
    assert "fetch_recent_emails" in BaseAgent._TOOL_HANDLERS
