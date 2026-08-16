# deprecated-mock-import (UP026)

Added in [v0.0.206](https://github.com/astral-sh/ruff/releases/tag/v0.0.206) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27deprecated-mock-import%27%20OR%20UP026)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyupgrade%2Frules%2Fdeprecated_mock_import.rs#L57)

Derived from the **[pyupgrade](../#pyupgrade-up)** linter.

Fix is always available.

## What it does

Checks for imports of the `mock` module that should be replaced with
`unittest.mock`.

## Why is this bad?

Since Python 3.3, `mock` has been a part of the standard library as
`unittest.mock`. The `mock` package is deprecated; use `unittest.mock`
instead.

## Example

```python
import mock
```

Use instead:

```python
from unittest import mock
```

## Options

This rule will not trigger if the `mock` import is required by the `isort` configuration.

- [`lint.isort.required-imports`](../../settings/#lint_isort_required-imports)

## References

- [Python documentation: `unittest.mock`](https://docs.python.org/3/library/unittest.mock.html)
- [PyPI: `mock`](https://pypi.org/project/mock/)
