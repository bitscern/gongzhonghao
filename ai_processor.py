"""AI evaluation and rewriting placeholder module."""

# 评分时 Prompt 必须要求：仅返回一个 0–100 的整数，严禁任何解释，以节省 Token。


def score_article(title: str, summary: str) -> int:
    """Score article 0–100. When integrating real model, prompt must require only a single number, no explanation."""
    return 0
