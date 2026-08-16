# comparison-of-constant (PLR0133)

Added in [v0.0.221](https://github.com/astral-sh/ruff/releases/tag/v0.0.221) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27comparison-of-constant%27%20OR%20PLR0133)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fcomparison_of_constant.rs#L30)

Derived from the **[Pylint](../#pylint-pl)** linter.

## What it does

Checks for comparisons between constants.

## Why is this bad?

Comparing two constants will always resolve to the same value, so the
comparison is redundant. Instead, the expression should be replaced
with the result of the comparison.

## Example

```python
foo = 1 == 1
```

Use instead:

```python
foo = True
```

## References

- [Python documentation: Comparisons](https://docs.python.org/3/reference/expressions.html#comparisons)
