import re
from typing import Optional, Tuple, List

# Patterns for sensitive keys, passwords, bearer tokens, and URLs
SECRET_PATTERNS = [
    (r"(AIzaSy[A-Za-z0-9_-]{33})", "GEMINI_API_KEY"),
    (r"\b(sk-(?:proj-)?[A-Za-z0-9_-]{20,})\b", "OPENAI_API_KEY"),
    (r"(?:bearer\s+)([A-Za-z0-9_\-\.]{20,})", "BEARER_TOKEN"),
    (r"(?:password|passwd|pwd|secret)[=:\s]+(['\"]?)([^'\"\s&]+)\1", "PASSWORD"),
    (r"(:[^:@\s]+)@([a-zA-Z0-9.-]+)", "DB_PASSWORD")
]

def mask_secret(secret: Optional[str], visible_prefix: int = 4, visible_suffix: int = 2) -> str:
    """
    Mask a sensitive token or key, leaving minimal prefix and suffix visible for debugging.
    e.g. AIzaSyB123456789...Z9 -> AIza***Z9
    """
    if not secret:
        return ""
    if len(secret) <= (visible_prefix + visible_suffix):
        return "***"
    return f"{secret[:visible_prefix]}***{secret[-visible_suffix:]}"

def sanitize_connection_string(conn_str: str) -> str:
    """
    Redact password in database URIs like postgresql://user:secret@host:5432/db -> postgresql://user:***@host:5432/db.
    """
    if not conn_str:
        return ""
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", conn_str)

def sanitize_log_message(msg: str) -> str:
    """
    Scan a log message and redact known sensitive signatures:
    - Gemini/Google API keys
    - Passwords and connection secrets
    - Bearer tokens
    """
    if not msg:
        return ""
    sanitized = sanitize_connection_string(msg)
    # Redact Google / Gemini API keys (AIzaSy...)
    sanitized = re.sub(r"AIzaSy[A-Za-z0-9_-]{33}", "AIzaSy***[MASKED_API_KEY]", sanitized)
    sanitized = re.sub(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b", "sk-***[MASKED_API_KEY]", sanitized)
    # Redact Authorization: Bearer tokens
    sanitized = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.]{20,}", r"\1***[MASKED_TOKEN]", sanitized)
    # Redact password fields in JSON or key-value format
    sanitized = re.sub(
        r"(?i)(password|passwd|secret)[\"']?\s*[:=]\s*[\"']?([^\"',\s]+)[\"']?",
        r'\1: "***[MASKED]"',
        sanitized
    )
    return sanitized

def verify_text_clean_of_secrets(text: str, forbidden_values: Optional[List[str]] = None) -> Tuple[bool, List[str]]:
    """
    Validates that a string (log output, error message, API response) does not contain forbidden raw secrets.
    """
    detected_leaks = []
    if forbidden_values:
        for secret in forbidden_values:
            if secret and len(secret) >= 6 and secret in text:
                detected_leaks.append(f"Contains literal forbidden secret (len={len(secret)})")

    # Check for unmasked Google API Key pattern
    if re.search(r"AIzaSy[A-Za-z0-9_-]{33}", text):
        detected_leaks.append("Found unmasked Google/Gemini API key")
    if re.search(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b", text):
        detected_leaks.append("Found unmasked OpenAI API key")

    # Check for unmasked database URI credentials
    if re.search(r"://[^:]+:[^@*]+@", text):
        detected_leaks.append("Found unmasked database password in URI")

    return (len(detected_leaks) == 0, detected_leaks)

