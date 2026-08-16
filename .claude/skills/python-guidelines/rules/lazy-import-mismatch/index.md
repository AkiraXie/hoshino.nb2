# lazy-import-mismatch (TID254)

Preview (since [0.15.6](https://github.com/astral-sh/ruff/releases/tag/0.15.6)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27lazy-import-mismatch%27%20OR%20TID254)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_tidy_imports%2Frules%2Flazy_import_mismatch.rs#L38)

Derived from the **[flake8-tidy-imports](../#flake8-tidy-imports-tid)** linter.

Fix is always available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Enforces the configured lazy-import policy in contexts where `lazy import`
is legal.

## Why is this bad?

Python 3.15 adds support for `lazy import` and `lazy from ... import ...`,
which defer the actual import work until the imported name is first used.

Depending on the policy, some modules should be imported lazily to defer
import work until the name is first used, while others should remain eager
to preserve import-time side effects.

This rule ignores contexts in which `lazy import` is invalid, such as
functions, classes, `try`/`except` blocks, `__future__` imports, and
`from ... import *` statements.

## Example

```python
import typing
```

Use instead:

```python
lazy import typing
```

## Options

- [`lint.flake8-tidy-imports.require-lazy`](../../settings/#lint_flake8-tidy-imports_require-lazy)
- [`lint.flake8-tidy-imports.ban-lazy`](../../settings/#lint_flake8-tidy-imports_ban-lazy)
