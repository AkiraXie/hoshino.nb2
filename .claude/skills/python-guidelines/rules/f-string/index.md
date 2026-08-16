# f-string (UP032)

Added in [v0.0.224](https://github.com/astral-sh/ruff/releases/tag/v0.0.224) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27f-string%27%20OR%20UP032)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyupgrade%2Frules%2Ff_strings.rs#L42)

Derived from the **[pyupgrade](../#pyupgrade-up)** linter.

Fix is sometimes available.

## What it does

Checks for `str.format` calls that can be replaced with f-strings.

## Why is this bad?

f-strings are more readable and generally preferred over `str.format`
calls.

## Example

```python
"{}".format(foo)
```

Use instead:

```python
f"{foo}"
```

## References

- [Python documentation: f-strings](https://docs.python.org/3/reference/lexical_analysis.html#f-strings)
