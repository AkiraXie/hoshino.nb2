# docstring-in-stub (PYI021)

Added in [v0.0.253](https://github.com/astral-sh/ruff/releases/tag/v0.0.253) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27docstring-in-stub%27%20OR%20PYI021)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_pyi%2Frules%2Fdocstring_in_stubs.rs#L29)

Derived from the **[flake8-pyi](../#flake8-pyi-pyi)** linter.

Fix is always available.

## What it does

Checks for the presence of docstrings in stub files.

## Why is this bad?

Stub files should omit docstrings, as they're intended to provide type
hints, rather than documentation.

## Example

```python
def func(param: int) -> str:
    """This is a docstring."""
    ...
```

Use instead:

```python
def func(param: int) -> str: ...
```
