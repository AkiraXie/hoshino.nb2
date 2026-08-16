# invalid-suppression-comment (RUF103)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27invalid-suppression-comment%27%20OR%20RUF103)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Finvalid_suppression_comment.rs#L27)

Fix is always available.

## What it does

Checks for invalid suppression comments

## Why is this bad?

Invalid suppression comments are ignored by Ruff, and should either
be fixed or removed to avoid confusion.

## Example

```python
# ruff: disable  # missing codes
```

Use instead:

```python
# ruff: disable[E501]
```

Or delete the invalid suppression comment.

## References

- [Ruff error suppression](https://docs.astral.sh/ruff/linter/#error-suppression)
