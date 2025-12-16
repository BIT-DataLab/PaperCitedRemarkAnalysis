"""Configuration defaults for reference-context extraction (Module 5)."""

from __future__ import annotations

import re
from typing import Final

DEFAULT_WINDOW: Final[int] = 512
DEFAULT_MATCH_THRESHOLD: Final[float] = 0.8

# Match a standalone heading line like:
#   References
#   **References**
#   ## References
#   ## **References**
# Also supports "Bibliography" equivalents (English only).
REFERENCES_HEADING_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*\s*(?:References|Bibliography)\s*\*\*|(?:References|Bibliography))\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Parse numbered reference entry starts in the References section, e.g.:
#   [4] Some author... Title...
REF_ENTRY_START_RE: Final[re.Pattern[str]] = re.compile(r"^\s*\[(\d+)\]\s+", re.MULTILINE)

# Numeric citation brackets in the main text (only):
#   [4]
#   [36, 42, 66, 87]
#   [36; 42; 66]
CITATION_BRACKET_RE: Final[re.Pattern[str]] = re.compile(r"\[\s*(\d+(?:\s*[,;]\s*\d+)*)\s*\]")

