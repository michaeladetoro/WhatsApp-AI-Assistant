"""
Fast-path regex responses.

These patterns are checked BEFORE the RAG chain is called.
If a message matches, a response is returned instantly (zero LLM latency).
Returns None if no pattern matches — the message should go to the RAG handler.

All branded text is intentionally kept as PLACEHOLDER comments.
Update the response strings to match your product/organisation.
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Pattern → response map (checked in order; first match wins).
# {username} is substituted at render time.
# ---------------------------------------------------------------------------
_FAST_RESPONSES: list[tuple[str, str]] = [
    # Greetings
    (
        r"^(hi|hello|hey|yo|howdy|good\s+(morning|afternoon|evening)|greetings|how\s+far|hi\s+there)[!\.\?]?$",
        "Hi {username}! 👋 I'm your AI assistant. Ask me anything and I'll do my best to help.",  # PLACEHOLDER — customise greeting
    ),
    # Goodbye / closing
    (
        r"^(bye|goodbye|see\s+you|later|ttyl|done|finish|that['']?s\s+all|exit)$",
        "Goodbye! 👋 Feel free to come back anytime you have questions.",
    ),
    # Thank you
    (
        r"^(thanks|thank\s+you|thx|ty|appreciate\s+(it|that)|cheers)$",
        "You're welcome! 😊 Is there anything else I can help you with?",
    ),
    # OK / acknowledgement
    (
        r"^(ok|okay|alright|noted|got\s+it|understood|sounds\s+good|perfect|cool|fine|sure)$",
        "Got it! Let me know if you have any other questions.",
    ),
    # Help / menu
    (
        r"^(help|help\s+me|i\s+need\s+help|what\s+can\s+you\s+do|menu|options|start)$",
        "I'm here to help! Just ask me a question and I'll search our knowledge base for the best answer.\n\n"
        "You can also send a *voice note* instead of typing.",  # PLACEHOLDER — add topic-specific hints
    ),
    # Support / contact  — PLACEHOLDER: update with your actual support contacts
    (
        r"\b(support|contact|customer\s*(care|service)|email|reach\s+you|speak\s+to\s+someone|talk\s+to\s+agent|human)\b",
        "*Need to speak to someone?*\n\n"
        "📧 Email: support@example.com\n"  # PLACEHOLDER
        "📞 Phone: +00 000 000 0000\n\n"  # PLACEHOLDER
        "Our team is available to help.",
    ),
    # Negative experience / issue
    (
        r"\b(not\s+working|broken|error|problem|issue|bug|wrong)\b",
        "I'm sorry to hear that! 😔 For technical issues, please reach out to our support team:\n\n"
        "📧 support@example.com",  # PLACEHOLDER
    ),
]


def get_fast_response(text: str, username: str = "there") -> Optional[str]:
    """
    Check the message against fast-path patterns.
    Returns a formatted response string, or None if no pattern matched.
    """
    text_clean = text.strip()
    for pattern, response in _FAST_RESPONSES:
        if re.search(pattern, text_clean, re.IGNORECASE):
            return response.format(username=username)
    return None
