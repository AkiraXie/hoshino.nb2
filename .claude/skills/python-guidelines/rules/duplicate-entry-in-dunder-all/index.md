# duplicate-entry-in-dunder-all (RUF068)

Preview (since [0.14.14](https://github.com/astral-sh/ruff/releases/tag/0.14.14)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27duplicate-entry-in-dunder-all%27%20OR%20RUF068)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Fduplicate_entry_in_dunder_all.rs#L50)

Fix is sometimes available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Detects duplicate elements in `__all__` definitions.

## Why is this bad?

Duplicate elements in `__all__` serve no purpose and can indicate copy-paste errors or
incomplete refactoring.

## Example

```python
__all__ = [
    "DatabaseConnection",
    "Product",
    "User",
    "DatabaseConnection",  # Duplicate
]
```

Use instead:

```python
__all__ = [
    "DatabaseConnection",
    "Product",
    "User",
]
```

## Fix Safety

This rule's fix is marked as unsafe if the replacement would remove comments attached to the
original expression, potentially losing important context or documentation.

For example:

```python
__all__ = [
    "PublicAPI",
    # TODO: Remove this in v2.0
    "PublicAPI",  # Deprecated alias
]
```
