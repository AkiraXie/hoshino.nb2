# non-pep604-annotation-optional (UP045)

Added in [0.12.0](https://github.com/astral-sh/ruff/releases/tag/0.12.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27non-pep604-annotation-optional%27%20OR%20UP045)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyupgrade%2Frules%2Fuse_pep604_annotation.rs#L116)

Derived from the **[pyupgrade](../#pyupgrade-up)** linter.

Fix is sometimes available.

## What it does

Check for `typing.Optional` annotations that can be rewritten based on [PEP 604](https://peps.python.org/pep-0604/) syntax.

## Why is this bad?

[PEP 604](https://peps.python.org/pep-0604/) introduced a new syntax for union type annotations based on the
`|` operator. This syntax is more concise and readable than the previous
`typing.Optional` syntax.

This rule is enabled when targeting Python 3.10 or later (see:
[`target-version`](../../settings/#target-version)). By default, it's *also* enabled for earlier Python
versions if `from __future__ import annotations` is present, as
`__future__` annotations are not evaluated at runtime. If your code relies
on runtime type annotations (either directly or via a library like
Pydantic), you can disable this behavior for Python versions prior to 3.10
by setting [`lint.pyupgrade.keep-runtime-typing`](../../settings/#lint_pyupgrade_keep-runtime-typing) to `true`.

## Example

```python
from typing import Optional

foo: Optional[int] = None
```

Use instead:

```python
foo: int | None = None
```

## Fix safety

This rule's fix is marked as unsafe, as it may lead to runtime errors
using libraries that rely on runtime type annotations, like Pydantic,
on Python versions prior to Python 3.10, or as it may remove comments if they
are present within the type annotation being rewritten. It may also lead to runtime
errors in unusual and likely incorrect type annotations where the type does not
support the `|` operator.

## Options

- [`target-version`](../../settings/#target-version)
- [`lint.pyupgrade.keep-runtime-typing`](../../settings/#lint_pyupgrade_keep-runtime-typing)
