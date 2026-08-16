# percent-format-invalid-format (F501)

Added in [v0.0.142](https://github.com/astral-sh/ruff/releases/tag/v0.0.142) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27percent-format-invalid-format%27%20OR%20F501)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyflakes%2Frules%2Fstrings.rs#L42)

Derived from the **[Pyflakes](../#pyflakes-f)** linter.

## What it does

Checks for invalid `printf`-style format strings.

## Why is this bad?

Conversion specifiers are required for `printf`-style format strings. These
specifiers must contain a `%` character followed by a conversion type.

## Example

```python
"Hello, %" % "world"
```

Use instead:

```python
"Hello, %s" % "world"
```

## References

- [Python documentation: `printf`-style String Formatting](https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting)
