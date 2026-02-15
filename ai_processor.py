"""AI evaluation module."""

# Prompt template for real model integration:
# You are a financial news scorer. Return ONLY one integer from 0 to 100.
# No explanation, no extra text, no punctuation.
SCORING_PROMPT_RULE = (
    "Return only one integer between 0 and 100. "
    "Do not output any explanation or extra text."
)


def score_article(title: str, summary: str) -> int:
    """Score article 0-100.

    Replace this stub with a real model call that applies SCORING_PROMPT_RULE.
    """
    return 0

