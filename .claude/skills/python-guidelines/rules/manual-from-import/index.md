# manual-from-import (PLR0402)

Added in [v0.0.155](https://github.com/astral-sh/ruff/releases/tag/v0.0.155) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27manual-from-import%27%20OR%20PLR0402)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fmanual_import_from.rs#L35)

Derived from the **[Pylint](../#pylint-pl)** linter.

Fix is sometimes available.

## What it does

Checks for submodule imports that are aliased to the submodule name.

## Why is this bad?

Using the `from` keyword to import the submodule is more concise and
readable.

## Example

```python
import concurrent.futures as futures
```

Use instead:

```python
from concurrent import futures
```

## Options

This rule will not trigger on imports required by the `isort` configuration.

- [`lint.isort.required-imports`](../../settings/#lint_isort_required-imports)

## References

- [Python documentation: Submodules](https://docs.python.org/3/reference/import.html#submodules)
