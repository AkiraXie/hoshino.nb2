# duplicate-value (B033)

Added in [v0.0.271](https://github.com/astral-sh/ruff/releases/tag/v0.0.271) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27duplicate-value%27%20OR%20B033)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_bugbear%2Frules%2Fduplicate_value.rs#L45)

Derived from the **[flake8-bugbear](../#flake8-bugbear-b)** linter.

Fix is sometimes available.

## What it does

Checks for set literals that contain duplicate items.

## Why is this bad?

In Python, sets are unordered collections of unique elements. Including a
duplicate item in a set literal is redundant, as the duplicate item will be
replaced with a single item at runtime.

## Example

```python
{1, 2, 3, 1}
```

Use instead:

```python
{1, 2, 3}
```

## Fix Safety

This rule's fix is marked as unsafe if the replacement would remove comments attached to the
original expression, potentially losing important context or documentation.

For example:

```python
{
    1,
    2,
    # Comment
    1,
}
```
