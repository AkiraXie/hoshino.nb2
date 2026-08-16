# duplicate-try-block-exception (B025)

Added in [v0.0.67](https://github.com/astral-sh/ruff/releases/tag/v0.0.67) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27duplicate-try-block-exception%27%20OR%20B025)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_bugbear%2Frules%2Fduplicate_exceptions.rs#L45)

Derived from the **[flake8-bugbear](../#flake8-bugbear-b)** linter.

## What it does

Checks for `try-except` blocks with duplicate exception handlers.

## Why is this bad?

Duplicate exception handlers are redundant, as the first handler will catch
the exception, making the second handler unreachable.

## Example

```python
try:
    ...
except ValueError:
    ...
except ValueError:
    ...
```

Use instead:

```python
try:
    ...
except ValueError:
    ...
```

## Fix safety

This rule's fix is marked as safe, unless the exception handler contains comments.

## References

- [Python documentation: `except` clause](https://docs.python.org/3/reference/compound_stmts.html#except-clause)
