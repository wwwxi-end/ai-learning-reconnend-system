def format_score(score):
    """格式化分数：整数保持整数，小数保留两位"""
    if score is None:
        return None
    if isinstance(score, float) and score.is_integer():
        return int(score)
    return round(score, 2)