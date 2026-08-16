# dict-get-with-none-default (SIM910)

Added in [v0.0.261](https://github.com/astral-sh/ruff/releases/tag/v0.0.261) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27dict-get-with-none-default%27%20OR%20SIM910)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_simplify%2Frules%2Fast_expr.rs#L98)

Derived from the **[flake8-simplify](../#flake8-simplify-sim)** linter.

Fix is always available.

## What it does

Checks for `dict.get()` calls that pass `None` as the default value.

## Why is this bad?

`None` is the default value for `dict.get()`, so it is redundant to pass it
explicitly.

## Example

```python
ages = {"Tom": 23, "Maria": 23, "Dog": 11}
age = ages.get("Cat", None)
```

Use instead:

```python
ages = {"Tom": 23, "Maria": 23, "Dog": 11}
age = ages.get("Cat")
```

## Fix safety

This rule's fix is marked as safe, unless the expression contains comments.

## References

- [Python documentation: `dict.get`](https://docs.python.org/3/library/stdtypes.html#dict.get)
