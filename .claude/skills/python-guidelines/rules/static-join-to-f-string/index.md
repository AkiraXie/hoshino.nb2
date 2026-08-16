# static-join-to-f-string (FLY002)

Added in [v0.0.266](https://github.com/astral-sh/ruff/releases/tag/v0.0.266) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27static-join-to-f-string%27%20OR%20FLY002)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflynt%2Frules%2Fstatic_join_to_fstring.rs#L41)

Derived from the **[flynt](../#flynt-fly)** linter.

Fix is always available.

## What it does

Checks for `str.join` calls that can be replaced with f-strings.

## Why is this bad?

f-strings are more readable and generally preferred over `str.join` calls.

## Example

```python
" ".join((foo, bar))
```

Use instead:

```python
f"{foo} {bar}"
```

## Fix safety

The fix is always marked unsafe because the evaluation of the f-string
expressions will default to calling the `__format__` method of each
object, whereas `str.join` expects each object to be an instance of
`str` and uses the corresponding string. Therefore it is possible for
the values of the resulting strings to differ, or for one expression
to raise an exception while the other does not.

## References

- [Python documentation: f-strings](https://docs.python.org/3/reference/lexical_analysis.html#f-strings)
