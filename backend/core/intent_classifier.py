import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class IntentClassifier:
    """
    High-Speed Zero-VRAM Intent Classifier.
    Analyzes user messages with fast structural semantic parsing and parameter extraction.
    Does NOT require a secondary model swap into VRAM, preserving zero-latency responsiveness.
    """

    DIGEST_PATTERNS = (
        r"\b(what did you (do|fix|change)|what happened (last night|yesterday|today)|any updates|recent (activity|actions|fixes)|background work)\b",
    )

    FINANCE_PATTERNS = (
        r"\b(stock|price|ticker|portfolio|crypto|bitcoin|btc|ethereum|eth|nvda|nvidia|aapl|tsla|gold|inr|market)\b",
    )

    RESEARCH_PATTERNS = (
        r"\b(deep research|investigate|find out about|compare libraries|literature review|read docs for)\b",
    )

    BOOKMARK_PATTERNS = (
        r"https?://[^\s]+",
        r"\b(bookmark|save link|read this link)\b",
    )

    REFACTOR_PATTERNS = (
        r"\b(refactor|fix code|repair project|improve code|run tests on)\b",
    )

    def classify(self, user_message: str, explicit_workflow: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts intent, confidence score, and contextual parameters in <1ms.
        """
        if explicit_workflow:
            return {
                "intent": explicit_workflow.upper(),
                "confidence": 1.0,
                "extracted_params": {}
            }

        text = user_message.lower().strip()

        # 1. Background Autonomous Activity Query
        for pat in self.DIGEST_PATTERNS:
            if re.search(pat, text):
                return {
                    "intent": "AUTONOMOUS_DIGEST",
                    "confidence": 0.95,
                    "extracted_params": {"query_type": "recent_activity"}
                }

        # 2. URL Bookmarking
        for pat in self.BOOKMARK_PATTERNS:
            urls = re.findall(r"https?://[^\s]+", user_message)
            if urls:
                return {
                    "intent": "BOOKMARK",
                    "confidence": 0.98,
                    "extracted_params": {"urls": urls}
                }
            if re.search(pat, text):
                return {
                    "intent": "BOOKMARK",
                    "confidence": 0.85,
                    "extracted_params": {}
                }

        # 3. Financial Market Query
        has_finance_asset = bool(re.search(r"\b(stock|stocks|portfolio|crypto|bitcoin|btc|ethereum|eth|nvda|nvidia|aapl|tsla|gold|inr|nasdaq|dow|sp500|s&p)\b", text))
        has_finance_action = bool(re.search(r"\b(price|ticker|quote|valuation|market cap|dividend|earnings|trading)\b", text))
        ticker_match = re.search(r"\b[A-Z]{2,5}(-[A-Z]{3})?\b", user_message)
        ticker = ticker_match.group(0) if ticker_match else None

        if has_finance_asset or (has_finance_action and (ticker or "market" in text)):
            return {
                "intent": "FINANCE",
                "confidence": 0.90 if (has_finance_asset or ticker) else 0.70,
                "extracted_params": {"ticker": ticker}
            }

        # 4. Deep Research Query
        for pat in self.RESEARCH_PATTERNS:
            if re.search(pat, text):
                return {
                    "intent": "RESEARCH",
                    "confidence": 0.88,
                    "extracted_params": {}
                }

        # 5. Direct Code Refactor Request
        for pat in self.REFACTOR_PATTERNS:
            if re.search(pat, text):
                return {
                    "intent": "CODE_REFACTOR",
                    "confidence": 0.85,
                    "extracted_params": {}
                }

        # Default conversational chat
        return {
            "intent": "ENDPOINT",
            "confidence": 0.70,
            "extracted_params": {}
        }


intent_classifier = IntentClassifier()
