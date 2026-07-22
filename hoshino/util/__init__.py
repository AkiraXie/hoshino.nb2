"""Small, dependency-free utility helpers."""

import unicodedata


def normalize_str(string: str) -> str:
    """Normalize a Unicode string and convert it to lowercase."""

    return unicodedata.normalize("NFKC", string).lower()


__all__ = ["normalize_str"]
