# invalid-rule-code (RUF102)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27invalid-rule-code%27%20OR%20RUF102)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Finvalid_rule_code.rs#L57)

Fix is always available.

## What it does

Checks for `noqa` codes that are invalid.

## Why is this bad?

Invalid rule codes serve no purpose and may indicate outdated code suppressions.

## Example

```python
import os  # noqa: XYZ999
```

Use instead:

```python
import os
```

Or if there are still valid codes needed:

```python
import os  # noqa: E402
```

## Options

This rule will flag rule codes that are unknown to Ruff, even if they are
valid for other tools. You can tell Ruff to ignore such codes by configuring
the list of known "external" rule codes with the following option:

- [`lint.external`](../../settings/#lint_external)
