# in-empty-collection (RUF060)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27in-empty-collection%27%20OR%20RUF060)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Fin_empty_collection.rs#L27)

## What it does

Checks for membership tests on empty collections (such as `list`, `tuple`, `set`, or `dict`).

## Why is this bad?

If the collection is always empty, the check is unnecessary and can be removed.

## Example

```python
if 1 not in set():
    print("got it!")
```

Use instead:

```python
print("got it!")
```
