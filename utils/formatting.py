"""
WhatsApp text formatting helpers.
"""

import re


def clean_for_whatsapp(text: str) -> str:
    """
    Sanitise text for WhatsApp display.
    - Convert markdown headings (## Title) to bold (*Title*)
    - Ensure bold/italic markers are WhatsApp-compatible (* not **)
    - Remove HTML tags if any slip through
    """
    if not text:
        return ""

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Convert markdown headings to bold
    text = re.sub(r"^#{1,3}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)

    # Convert **bold** to *bold* (WhatsApp uses single asterisk)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)

    # Collapse excessive blank lines (max 2 consecutive newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def truncate(text: str, max_len: int = 4096) -> str:
    """Truncate text to WhatsApp's max message length."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
