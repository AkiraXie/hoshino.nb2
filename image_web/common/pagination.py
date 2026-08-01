def paginate(items: list, page: int, size: int) -> tuple[int, list]:
    """返回 (total, 当前页切片)。"""
    total = len(items)
    start = (page - 1) * size
    return total, items[start : start + size]
