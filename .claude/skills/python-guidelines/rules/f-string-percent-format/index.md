# f-string-percent-format (RUF073)

Preview (since [0.15.8](https://github.com/astral-sh/ruff/releases/tag/0.15.8)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27f-string-percent-format%27%20OR%20RUF073)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Ffstring_percent_format.rs#L29)

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for uses of the `%` operator on f-strings.

## Why is this bad?

F-strings already support interpolation via `{...}` expressions.
Using the `%` operator on an f-string is almost certainly a mistake,
since the f-string's interpolation and `%`-formatting serve the same
purpose. This typically indicates that the developer intended to use
either an f-string or `%`-formatting, but not both.

## Example

```python
f"{name}" % name
f"hello %s %s" % (first, second)
```

Use instead:

```python
f"{name}"
f"hello {first} {second}"
```
