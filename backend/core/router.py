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


def _word_match(text: str, keywords: tuple) -> bool:
    """True if any keyword appears as a whole word (or URL prefix) in text."""
    for kw in keywords:
        # URL prefixes matched as-is; everything else needs word boundaries
        if kw.startswith("http"):
            if kw in text:
                return True
        else:
            if re.search(rf'\b{re.escape(kw)}\b', text):
                return True
    return False


class IntentRouter:
    """
    Dynamic Intent Router Engine.
    Analyzes prompt inputs and routes to specialized agents dynamically,
    keeping system prompts lightweight and context windows clean.
    """

    # Finance keywords require BOTH a finance-intent word AND a ticker/asset word
    FINANCE_INTENT_WORDS = (
        "stock", "price", "ticker", "portfolio", "invest", "trading",
        "dividend", "valuation", "market cap", "shares", "crypto",
        "coin", "forex", "quote",
    )
    FINANCE_ASSET_WORDS = (
        "bitcoin", "btc", "ethereum", "eth", "nvda", "nvidia", "aapl",
        "tsla", "gold", "silver", "nifty", "sensex", "inr", "ruble", "euro",
    )
    RESEARCH_KEYWORDS = (
        "research", "deep search", "crawl", "find out", "analyze", "investigate",
        "overview", "paper", "documentation",
    )
    BOOKMARK_KEYWORDS = ("http://", "https://", "bookmark", "save link", "read link")

    @classmethod
    def classify_intent(cls, prompt: str, explicit_workflow: Optional[str] = None) -> str:
        """
        Classifies incoming prompt using hybrid intent analysis:
        1. Fast semantic IntentClassifier evaluation.
        2. Deterministic word-boundary keyword matching fallback.
        Logs when the two paths disagree (useful for tuning).
        """
        if explicit_workflow and explicit_workflow.upper() in AgentRegistry._registry and explicit_workflow.upper() != "ENDPOINT":
            return explicit_workflow.upper()

        llm_intent = None
        try:
            from core.intent_classifier import intent_classifier
            res = intent_classifier.classify(prompt, explicit_workflow)
            if res.get("confidence", 0) >= 0.75:
                candidate = res.get("intent", "ENDPOINT")
                if candidate != "AUTONOMOUS_DIGEST" and candidate in AgentRegistry._registry:
                    llm_intent = candidate
        except Exception as e:
            logger.debug(f"IntentClassifier fallback: {e}")

        keyword_intent = cls._keyword_classify(prompt)

        # If both paths agree, no logging needed
        if llm_intent and llm_intent == keyword_intent:
            return llm_intent

        # LLM path wins if confident; keyword is fallback
        if llm_intent:
            if llm_intent != keyword_intent:
                logger.debug(
                    f"Intent routing disagreement: LLM='{llm_intent}' "
                    f"keyword='{keyword_intent}' — using LLM result. "
                    f"Prompt prefix: {prompt[:60]!r}"
                )
            return llm_intent

        return keyword_intent

    @classmethod
    def _keyword_classify(cls, prompt: str) -> str:
        """Word-boundary keyword classification. Avoids substring false matches."""
        text = prompt.lower()

        # 0. Desktop / CUA intent
        has_file_kw = _word_match(text, ("file", "files", "filew", "txt", "md", "document", "notepad", "script")) or any(
            w.startswith("file") for w in re.findall(r"\b\w+\b", text)
        )
        has_action_kw = _word_match(text, ("create", "write", "make", "save", "open",
                                           "launch", "type", "click", "screenshot", "window"))
        has_desktop_loc = "desktop" in text or text.startswith("/desktop") or text.startswith("/cua")

        if (
            text.startswith("/desktop")
            or text.startswith("/cua")
            or (has_desktop_loc and has_file_kw and has_action_kw)
        ):
            return "CUA"

        # 1. URL Bookmark intent
        if any(kw in text for kw in ("http://", "https://")) or _word_match(
            text, ("bookmark", "save link", "read link")
        ):
            return "BOOKMARK"

        # 2. Finance intent — require BOTH a finance-intent word AND an asset word
        # (prevents "what's the weather in AAPL, Iowa?" from triggering)
        has_intent = _word_match(text, cls.FINANCE_INTENT_WORDS)
        has_asset = _word_match(text, cls.FINANCE_ASSET_WORDS)
        if has_intent and has_asset:
            return "FINANCE"

        # 3. Research intent
        if _word_match(text, cls.RESEARCH_KEYWORDS):
            return "RESEARCH"

        return "ENDPOINT"

    @classmethod
    def resolve_agent(cls, prompt: str, explicit_workflow: Optional[str] = None) -> Type[BaseAgent]:
        intent = cls.classify_intent(prompt, explicit_workflow)
        agent_cls = AgentRegistry.get(intent)
        if not agent_cls:
            agent_cls = AgentRegistry.get("ENDPOINT")
        return agent_cls
