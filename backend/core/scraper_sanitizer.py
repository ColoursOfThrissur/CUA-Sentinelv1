"""
Air-Gapped Scraper Sanitizer Module for CUA-Sentinel.

Sanitizes raw web text to neutralize indirect prompt injection attacks
and malicious instructions before text enters main model context.
"""

import re
import logging
from typing import Dict, Any, Tuple, Optional, Set
from urllib.parse import urlparse

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

def mask_sensitive_data(val: Any) -> Any:
    """
    R5 Data Masking:
    Masks account numbers, credit cards / PAN-style numbers, email addresses, and passwords in logs/traces.
    """
    if isinstance(val, str):
        # Mask emails: j***e@example.com
        val = re.sub(r'([a-zA-Z0-9_.+-])[a-zA-Z0-9_.+-]*@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', r'\1***@\2', val)
        # Mask 12-16 digit numbers (account / card numbers)
        val = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{2,4}[-\s]?\d{2,4}\b', r'****-****-****-****', val)
        # Mask passwords / secret tokens
        val = re.sub(r'(?i)(password|secret|app_password|token|key)\s*[:=]\s*["\']?[^"\'\s,]+["\']?', r'\1=***MASKED***', val)
        return val
    elif isinstance(val, dict):
        return {k: mask_sensitive_data(v) if k not in ("password", "secret", "app_password", "token", "key") else "***MASKED***" for k, v in val.items()}
    elif isinstance(val, list):
        return [mask_sensitive_data(item) for item in val]
    return val


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

    def mask(self, data: Any) -> Any:
        return mask_sensitive_data(data)

scraper_sanitizer = ScraperSanitizer()


def neutralize_output(text: str, allowed_urls: Optional[Set[str]] = None) -> str:
    """
    Centralized Output Neutralizer:
    1. Strips remote markdown images (![alt](url)) to prevent exfiltration / beaconing.
    2. Normalizes link text with hostnames for approved URLs.
    3. Removes unapproved URLs not present in allowed_urls (or localhost/127.0.0.1),
       replacing them with [link removed: hostname].
    4. Handles trailing punctuation cleanly.
    """
    if not text or not isinstance(text, str):
        return text or ""

    allowed_set = set(allowed_urls or [])

    # Helper: Normalize and check if a given URL is permitted
    def _is_allowed(target_url: str) -> Tuple[bool, str]:
        try:
            parsed = urlparse(target_url.strip())
            domain = parsed.netloc.lower()
        except Exception:
            return False, "invalid"

        if not domain:
            return False, ""

        # Localhost / 127.0.0.1 is always permitted (local reports, downloads, dashboard)
        base_domain = domain.split(":")[0]
        if base_domain in ("localhost", "127.0.0.1"):
            return True, domain

        # Check against allowed URLs
        target_clean = target_url.rstrip("/")
        for a_url in allowed_set:
            if not a_url:
                continue
            try:
                a_parsed = urlparse(a_url.strip())
                a_domain = a_parsed.netloc.lower() or a_url.lower()
                a_clean = a_url.rstrip("/")
                if domain == a_domain or domain.endswith("." + a_domain):
                    return True, domain
                if target_clean == a_clean:
                    return True, domain
            except Exception:
                continue

        return False, domain

    # Step 1: Strip remote markdown images: ![alt](url) -> [image suppressed]
    # We strip all remote images to avoid markdown image rendering triggers in frontend / Discord.
    text = re.sub(r'!\[([^\]]*)\]\((https?://[^\s\)]+)\)', r'[image suppressed]', text)

    # Step 2: Process markdown links: [label](url)
    def _replace_md_link(match):
        label = match.group(1)
        raw_url = match.group(2).strip()

        # Separate any trailing punctuation inside parentheses if present
        allowed, domain = _is_allowed(raw_url)
        if allowed:
            # If domain isn't in label, append (domain) to label
            if domain and domain not in label.lower():
                return f"[{label} ({domain})]({raw_url})"
            return f"[{label}]({raw_url})"
        else:
            return f"{label} [link removed: {domain or 'untrusted'}]"

    # Match markdown links: [label](http...)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)', _replace_md_link, text)

    # Step 3: Process bare URLs: http(s)://...
    # Avoid matching URLs that are already part of markdown links `](https://...)`
    def _replace_bare_url(match):
        full_match = match.group(0)
        # Separate trailing punctuation
        trailing = ""
        url_core = full_match
        while url_core and url_core[-1] in ".,;:!?)'\"":
            trailing = url_core[-1] + trailing
            url_core = url_core[:-1]

        allowed, domain = _is_allowed(url_core)
        if allowed:
            return url_core + trailing
        else:
            return f"[link removed: {domain or 'untrusted'}]{trailing}"

    text = re.sub(r'(?<!\]\()(https?://[^\s<>"]+)', _replace_bare_url, text)

    return text

