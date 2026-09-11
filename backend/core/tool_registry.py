import logging
from typing import Dict, List, Any, Optional, Callable

logger = logging.getLogger(__name__)


class CapabilityMetadata:
    """Metadata describing an agent or tool capability."""

    def __init__(
        self,
        capability_id: str,
        name: str,
        description: str,
        explicit_hints: List[str],
        handler: Optional[Callable] = None,
    ):
        self.capability_id = capability_id.upper()
        self.name = name
        self.description = description
        self.explicit_hints = [h.lower() for h in explicit_hints]
        self.handler = handler

    def to_prompt_line(self) -> str:
        return f"- [{self.capability_id}] ({self.name}): {self.description}"


class ToolRegistry:
    """
    Universal Registry for Agent Capabilities and Tools.
    Provides auto-updating context prompts for LLMs (qwen3_5_9b)
    and clean dynamic lookup when new tools/agents are registered.
    """

    _capabilities: Dict[str, CapabilityMetadata] = {}

    @classmethod
    def register(
        cls,
        capability_id: str,
        name: str,
        description: str,
        explicit_hints: List[str],
        handler: Optional[Callable] = None,
    ) -> None:
        cap = CapabilityMetadata(capability_id, name, description, explicit_hints, handler)
        cls._capabilities[cap.capability_id] = cap
        logger.info(f"Registered tool capability: {cap.capability_id} -> {cap.name}")

    @classmethod
    def get(cls, capability_id: str) -> Optional[CapabilityMetadata]:
        return cls._capabilities.get(capability_id.upper())

    @classmethod
    def detect_explicit_capabilities(cls, prompt: str) -> List[CapabilityMetadata]:
        """
        Detects if user explicitly specified a capability via hint words.
        """
        text = prompt.lower()
        matched = []
        for cap in cls._capabilities.values():
            if any(hint in text for hint in cap.explicit_hints):
                matched.append(cap)
        return matched

    @classmethod
    def get_capabilities_prompt(cls) -> str:
        """
        Generates auto-updating capabilities context block for qwen3_5_9b.
        """
        if not cls._capabilities:
            return ""

        lines = ["AVAILABLE SYSTEM CAPABILITIES & TOOLS:"]
        for cap in cls._capabilities.values():
            lines.append(cap.to_prompt_line())

        return "\n".join(lines)

    @classmethod
    def get_relevant_capabilities_prompt(cls, prompt: str, max_tools: int = 2) -> str:
        """
        Dynamic Tool Routing (RAG for Tools):
        Filters tools dynamically based on user prompt relevance to inject only
        1-2 relevant tool schemas into qwen3_5_9b system prompt, protecting 12GB VRAM context.
        """
        if not cls._capabilities:
            return ""

        # Check explicit hint matches first
        explicit_matches = cls.detect_explicit_capabilities(prompt)
        selected = list(explicit_matches)

        # Fill remaining slots with keyword relevance scoring
        if len(selected) < max_tools:
            words = set(prompt.lower().split())
            scored = []
            for cap in cls._capabilities.values():
                if cap in selected:
                    continue
                score = 0
                desc_words = set(cap.description.lower().split())
                score += len(words.intersection(desc_words)) * 2
                for hint in cap.explicit_hints:
                    if any(w in hint for w in words):
                        score += 3
                scored.append((score, cap))
            
            scored.sort(key=lambda x: x[0], reverse=True)
            for score, cap in scored:
                if len(selected) >= max_tools:
                    break
                selected.append(cap)

        if not selected:
            selected = list(cls._capabilities.values())[:max_tools]

        lines = ["DYNAMICALLY ROUTED TOOLS (12GB VRAM Optimized):"]
        for cap in selected:
            lines.append(cap.to_prompt_line())

        return "\n".join(lines)


# Pre-register built-in core capabilities
ToolRegistry.register(
    capability_id="GMAIL_INBOX",
    name="Gmail Engine",
    description="Accesses user's Gmail inbox to fetch emails, order updates, receipts, invoices, flight bookings, warranty claims, support tickets, or tracking numbers.",
    explicit_hints=["gmail", "inbox", "check my email", "search email", "my email", "order receipt", "warranty claim", "flight ticket", "invoice details"],
)

ToolRegistry.register(
    capability_id="WEB_SEARCH",
    name="Web Search Engine",
    description="Searches the live web for technical documentation, current news, latest prices, or general online answers.",
    explicit_hints=["web", "search web", "google", "look up online", "internet", "latest news", "current price"],
)

ToolRegistry.register(
    capability_id="FINANCE_MARKET",
    name="Finance & Stock Quotes",
    description="Fetches live stock ticker prices, crypto quotes (BTC, ETH), and portfolio valuations.",
    explicit_hints=["stock", "ticker", "portfolio", "crypto", "price of nvda", "price of aapl", "bitcoin price"],
)

ToolRegistry.register(
    capability_id="LINK_INDEXER",
    name="URL Bookmark & RAG Indexer",
    description="Crawls, summarizes, and indexes web URLs into local RAG vector memory for context retrieval.",
    explicit_hints=["http://", "https://", "bookmark link", "save url"],
)

ToolRegistry.register(
    capability_id="CUA_DESKTOP",
    name="Computer Use Agent (CUA)",
    description="Interacts with Windows desktop apps, enumerates UI controls, captures screenshots, and automates UI clicks/typing.",
    explicit_hints=["screenshot", "click button", "open app", "desktop control", "type text"],
)
