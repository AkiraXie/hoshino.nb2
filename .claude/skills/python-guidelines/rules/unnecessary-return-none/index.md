# unnecessary-return-none (RET501)

Added in [v0.0.154](https://github.com/astral-sh/ruff/releases/tag/v0.0.154) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27unnecessary-return-none%27%20OR%20RET501)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_return%2Frules%2Ffunction.rs#L64)

Derived from the **[flake8-return](../#flake8-return-ret)** linter.

Fix is always available.

## What it does

Checks for the presence of a `return None` statement when `None` is the only
possible return value.

## Why is this bad?

Python implicitly assumes `return None` if an explicit `return` value is
omitted. Therefore, explicitly returning `None` is redundant and should be
avoided when it is the only possible `return` value across all code paths
in a given function.

## Example

```python
def foo(bar):
    if not bar:
        return
    return None
```

Use instead:

```python
def foo(bar):
    if not bar:
        return
    return
```

## Fix safety

This rule's fix is marked as unsafe for cases in which comments would be
dropped from the `return` statement.

## Options

This rule ignores functions marked as properties.

- [`lint.pydocstyle.property-decorators`](../../settings/#lint_pydocstyle_property-decorators)
