# percent-format-missing-argument (F505)

Added in [v0.0.142](https://github.com/astral-sh/ruff/releases/tag/v0.0.142) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27percent-format-missing-argument%27%20OR%20F505)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyflakes%2Frules%2Fstrings.rs#L200)

Derived from the **[Pyflakes](../#pyflakes-f)** linter.

## What it does

Checks for named placeholders in `printf`-style format strings that are not
present in the provided mapping.

## Why is this bad?

Named placeholders that lack a corresponding value in the provided mapping
will raise a `KeyError`.

## Example

```python
"%(greeting)s, %(name)s" % {"name": "world"}
```

Use instead:

```python
"Hello, %(name)s" % {"name": "world"}
```

## References

- [Python documentation: `printf`-style String Formatting](https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting)
