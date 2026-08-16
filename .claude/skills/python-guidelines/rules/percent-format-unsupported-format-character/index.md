# percent-format-unsupported-format-character (F509)

Added in [v0.0.142](https://github.com/astral-sh/ruff/releases/tag/v0.0.142) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27percent-format-unsupported-format-character%27%20OR%20F509)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyflakes%2Frules%2Fstrings.rs#L342)

Derived from the **[Pyflakes](../#pyflakes-f)** linter.

## What it does

Checks for `printf`-style format strings with invalid format characters.

## Why is this bad?

In `printf`-style format strings, the `%` character is used to indicate
placeholders. If a `%` character is not followed by a valid format
character, it will raise a `ValueError` at runtime.

## Example

```python
"Hello, %S" % "world"
```

Use instead:

```python
"Hello, %s" % "world"
```

## References

- [Python documentation: `printf`-style String Formatting](https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting)
