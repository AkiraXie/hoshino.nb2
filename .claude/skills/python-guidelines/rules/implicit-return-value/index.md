# implicit-return-value (RET502)

Added in [v0.0.154](https://github.com/astral-sh/ruff/releases/tag/v0.0.154) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27implicit-return-value%27%20OR%20RET502)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_return%2Frules%2Ffunction.rs#L106)

Derived from the **[flake8-return](../#flake8-return-ret)** linter.

Fix is always available.

## What it does

Checks for the presence of a `return` statement with no explicit value,
for functions that return non-`None` values elsewhere.

## Why is this bad?

Including a `return` statement with no explicit value can cause confusion
when other `return` statements in the function return non-`None` values.
Python implicitly assumes return `None` if no other return value is present.
Adding an explicit `return None` can make the code more readable by clarifying
intent.

## Example

```python
def foo(bar):
    if not bar:
        return
    return 1
```

Use instead:

```python
def foo(bar):
    if not bar:
        return None
    return 1
```
