"""
Air-Gapped Scraper Sanitizer Module for CUA-Sentinel.

Sanitizes raw web text to neutralize indirect prompt injection attacks
and malicious instructions before text enters main model context.
"""

import re
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

SUSPICIOUS_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?prior\s+prompts",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
    r"system\s+override",
    r"rm\s+-rf",
    r"delete\s+all\s+files",
    r"format\s+c:",
    r"drop\s+table",
    r"eval\(",
    r"exec\(",
]

class ScraperSanitizer:
    def sanitize_text(self, raw_text: str) -> Tuple[str, bool, int]:
        """
        Sanitizes input text by removing prompt injection attempts.
        Returns (clean_text, was_modified, detections_count).
        """
        if not raw_text:
            return "", False, 0

        clean_text = raw_text
        detections = 0

        for pattern in SUSPICIOUS_PATTERNS:
            matches = len(re.findall(pattern, clean_text, flags=re.IGNORECASE))
            if matches > 0:
                detections += matches
                clean_text = re.sub(
                    pattern,
                    "[SANITIZED: INJECTION ATTEMPT STRIPPED]",
                    clean_text,
                    flags=re.IGNORECASE
                )

        if detections > 0:
            logger.warning(f"ScraperSanitizer neutralized {detections} suspicious prompt injection patterns.")

        return clean_text, (detections > 0), detections

scraper_sanitizer = ScraperSanitizer()
