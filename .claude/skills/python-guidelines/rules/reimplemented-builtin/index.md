# reimplemented-builtin (SIM110)

Added in [v0.0.211](https://github.com/astral-sh/ruff/releases/tag/v0.0.211) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27reimplemented-builtin%27%20OR%20SIM110)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_simplify%2Frules%2Freimplemented_builtin.rs#L54)

Derived from the **[flake8-simplify](../#flake8-simplify-sim)** linter.

Fix is sometimes available.

## What it does

Checks for `for` loops that can be replaced with a builtin function, like
`any` or `all`.

## Why is this bad?

Using a builtin function is more concise and readable.

## Example

```python
def foo():
    for item in iterable:
        if predicate(item):
            return True
    return False
```

Use instead:

```python
def foo():
    return any(predicate(item) for item in iterable)
```

## Fix safety

This fix is always marked as unsafe because it might remove comments.

## Options

The rule will avoid flagging cases where using the builtin function would exceed the configured
line length, as determined by these options:

- [`lint.pycodestyle.max-line-length`](../../settings/#lint_pycodestyle_max-line-length)
- [`indent-width`](../../settings/#indent-width)

## References

- [Python documentation: `any`](https://docs.python.org/3/library/functions.html#any)
- [Python documentation: `all`](https://docs.python.org/3/library/functions.html#all)
