# useless-import-alias (PLC0414)

Added in [v0.0.156](https://github.com/astral-sh/ruff/releases/tag/v0.0.156) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27useless-import-alias%27%20OR%20PLC0414)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fuseless_import_alias.rs#L43)

Derived from the **[Pylint](../#pylint-pl)** linter.

Fix is sometimes available.

## What it does

Checks for import aliases that do not rename the original package.
This rule does not apply in `__init__.py` files.

## Why is this bad?

The import alias is redundant and should be removed to avoid confusion.

## Fix safety

This fix is marked as always unsafe because the user may be intentionally
re-exporting the import. While statements like `import numpy as numpy`
appear redundant, they can have semantic meaning in certain contexts.

## Example

```python
import numpy as numpy
```

Use instead:

```python
import numpy as np
```

or

```python
import numpy
```

## Options

The rule will emit a diagnostic but not a fix if the import is required by the `isort`
configuration option:

- [`lint.isort.required-imports`](../../settings/#lint_isort_required-imports)
