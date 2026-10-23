"""Redaction is applied after formatting and includes exception messages."""

import logging
import re

PATTERNS = [
    (r"(?i)(authorization[\s\"':=]+)(?:bearer\s+|basic\s+)?[^\s,}\"']+", r"\1[REDACTED]"),
    (
        r"(?i)((?:api[_-]?key|password|secret|token|seed)[\w-]*[\s\"':=]+)[^\s,}\"']+",
        r"\1[REDACTED]",
    ),
    (
        r"\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})\b",
        "[REDACTED]",
    ),
    (r"https?://[^\s/@]+:[^\s/@]+@", "https://[REDACTED]@"),
    (r"(?i)([?&](?:key|token|secret|password)=)[^&\s]+", r"\1[REDACTED]"),
]


def redact(text: str) -> str:
    for pattern, replacement in PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for handler in root.handlers:
        handler.setFormatter(RedactingFormatter("%(levelname)s:%(name)s:%(message)s"))
