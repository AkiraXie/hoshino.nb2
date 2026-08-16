# open-alias (UP020)

Added in [v0.0.196](https://github.com/astral-sh/ruff/releases/tag/v0.0.196) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27open-alias%27%20OR%20UP020)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyupgrade%2Frules%2Fopen_alias.rs#L35)

Derived from the **[pyupgrade](../#pyupgrade-up)** linter.

Fix is sometimes available.

## What it does

Checks for uses of `io.open`.

## Why is this bad?

In Python 3, `io.open` is an alias for `open`. Prefer using `open` directly,
as it is more idiomatic.

## Example

```python
import io

with io.open("file.txt") as f:
    ...
```

Use instead:

```python
with open("file.txt") as f:
    ...
```

## Fix safety

This rule's fix is marked as safe, unless the expression contains comments.

## References

- [Python documentation: `io.open`](https://docs.python.org/3/library/io.html#io.open)
