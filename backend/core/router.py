import logging
import re
from typing import Any, Dict, Optional, Type
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Registry for dynamic agent lookup and registration.
    Adding a new agent capability requires only registering it here.
    """

    _registry: Dict[str, Type[BaseAgent]] = {}

    @classmethod
    def register(cls, intent_name: str, agent_class: Type[BaseAgent]) -> None:
        cls._registry[intent_name.upper()] = agent_class
        logger.info(f"Registered agent capability: {intent_name.upper()} -> {agent_class.__name__}")

    @classmethod
    def get(cls, intent_name: str) -> Optional[Type[BaseAgent]]:
        return cls._registry.get(intent_name.upper())

    @classmethod
    def list_capabilities(cls) -> Dict[str, str]:
        return {k: v.__name__ for k, v in cls._registry.items()}


class IntentRouter:
    """
    Dynamic Intent Router Engine.
    Analyzes prompt inputs and routes to specialized agents dynamically,
    keeping system prompts lightweight and context windows clean.
    """

    FINANCE_KEYWORDS = (
        "stock", "price", "ticker", "portfolio", "crypto", "value",
        "bitcoin", "btc", "ethereum", "eth", "nvda", "nvidia", "aapl",
        "tsla", "gold", "market", "forex", "inr", "ruble", "euro",
    )
    RESEARCH_KEYWORDS = (
        "research", "deep search", "crawl", "find out", "analyze", "investigate",
        "overview", "paper", "documentation",
    )
    BOOKMARK_KEYWORDS = ("http://", "https://", "bookmark", "save link", "read link")

    @classmethod
    def classify_intent(cls, prompt: str, explicit_workflow: Optional[str] = None) -> str:
        """
        Classifies incoming prompt into targeted capability intent.
        """
        if explicit_workflow and explicit_workflow.upper() in AgentRegistry._registry:
            return explicit_workflow.upper()

        text = prompt.lower()

        # 1. URL Bookmark Intent
        if any(kw in text for kw in cls.BOOKMARK_KEYWORDS):
            return "BOOKMARK"

        # 2. Finance Intent
        if any(kw in text for kw in cls.FINANCE_KEYWORDS):
            return "FINANCE"

        # 3. Deep Research Intent
        if any(kw in text for kw in cls.RESEARCH_KEYWORDS):
            return "RESEARCH"

        # Default fast path
        return "ENDPOINT"

    @classmethod
    def resolve_agent(cls, prompt: str, explicit_workflow: Optional[str] = None) -> Type[BaseAgent]:
        intent = cls.classify_intent(prompt, explicit_workflow)
        agent_cls = AgentRegistry.get(intent)
        if not agent_cls:
            agent_cls = AgentRegistry.get("ENDPOINT")
        return agent_cls
