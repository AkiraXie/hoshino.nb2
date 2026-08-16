# duplicate-literal-member (PYI062)

Added in [0.6.0](https://github.com/astral-sh/ruff/releases/tag/0.6.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27duplicate-literal-member%27%20OR%20PYI062)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_pyi%2Frules%2Fduplicate_literal_member.rs#L42)

Derived from the **[flake8-pyi](../#flake8-pyi-pyi)** linter.

Fix is always available.

## What it does

Checks for duplicate members in a `typing.Literal[]` slice.

## Why is this bad?

Duplicate literal members are redundant and should be removed.

## Example

```python
from typing import Literal

foo: Literal["a", "b", "a"]
```

Use instead:

```python
from typing import Literal

foo: Literal["a", "b"]
```

## Fix safety

This rule's fix is marked as safe, unless the type annotation contains comments.

Note that while the fix may flatten nested literals into a single top-level literal,
the semantics of the annotation will remain unchanged.

## References

- [Python documentation: `typing.Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)
