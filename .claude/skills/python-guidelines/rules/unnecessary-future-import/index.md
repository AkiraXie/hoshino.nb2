# unnecessary-future-import (UP010)

Added in [v0.0.155](https://github.com/astral-sh/ruff/releases/tag/v0.0.155) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27unnecessary-future-import%27%20OR%20UP010)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyupgrade%2Frules%2Funnecessary_future_import.rs#L46)

Derived from the **[pyupgrade](../#pyupgrade-up)** linter.

Fix is always available.

## What it does

Checks for unnecessary `__future__` imports.

## Why is this bad?

The `__future__` module is used to enable features that are not yet
available in the current Python version. If a feature is already
available in the minimum supported Python version, importing it
from `__future__` is unnecessary and should be removed to avoid
confusion.

## Example

```python
from __future__ import print_function

print("Hello, world!")
```

Use instead:

```python
print("Hello, world!")
```

## Fix safety

This fix is marked unsafe if applying it would delete a comment.

## Options

- [`target-version`](../../settings/#target-version)

## References

- [Python documentation: `__future__` — Future statement definitions](https://docs.python.org/3/library/__future__.html)
