# native-literals (UP018)

Added in [v0.0.193](https://github.com/astral-sh/ruff/releases/tag/v0.0.193) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27native-literals%27%20OR%20UP018)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyupgrade%2Frules%2Fnative_literals.rs#L143)

Derived from the **[pyupgrade](../#pyupgrade-up)** linter.

Fix is always available.

## What it does

Checks for unnecessary calls to `str`, `bytes`, `int`, `float`, `bool`, and `complex`.

## Why is this bad?

The mentioned constructors can be replaced with their respective literal
forms, which are more readable and idiomatic.

## Example

```python
str("foo")
```

Use instead:

```python
"foo"
```

## Fix safety

The fix is marked as unsafe if it might remove comments.

## References

- [Python documentation: `str`](https://docs.python.org/3/library/stdtypes.html#str)
- [Python documentation: `bytes`](https://docs.python.org/3/library/stdtypes.html#bytes)
- [Python documentation: `int`](https://docs.python.org/3/library/functions.html#int)
- [Python documentation: `float`](https://docs.python.org/3/library/functions.html#float)
- [Python documentation: `bool`](https://docs.python.org/3/library/functions.html#bool)
- [Python documentation: `complex`](https://docs.python.org/3/library/functions.html#complex)
