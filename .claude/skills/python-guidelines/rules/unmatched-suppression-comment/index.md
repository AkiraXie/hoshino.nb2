# unmatched-suppression-comment (RUF104)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27unmatched-suppression-comment%27%20OR%20RUF104)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Funmatched_suppression_comment.rs#L33)

## What it does

Checks for unmatched range suppression comments

## Why is this bad?

Unmatched range suppression comments can inadvertently suppress violations
over larger sections of code than intended, particularly at module scope.

## Example

```python
def foo():
    # ruff: disable[E501]  # unmatched
    REALLY_LONG_VALUES = [...]

    print(REALLY_LONG_VALUES)
```

Use instead:

```python
def foo():
    # ruff: disable[E501]
    REALLY_LONG_VALUES = [...]
    # ruff: enable[E501]

    print(REALLY_LONG_VALUES)
```

## References

- [Ruff error suppression](https://docs.astral.sh/ruff/linter/#error-suppression)
