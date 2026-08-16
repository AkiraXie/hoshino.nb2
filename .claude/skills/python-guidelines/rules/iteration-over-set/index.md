# iteration-over-set (PLC0208)

Added in [v0.0.271](https://github.com/astral-sh/ruff/releases/tag/v0.0.271) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27iteration-over-set%27%20OR%20PLC0208)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fiteration_over_set.rs#L32)

Derived from the **[Pylint](../#pylint-pl)** linter.

Fix is always available.

## What it does

Checks for iteration over a `set` literal in which each element is a literal.

## Why is this bad?

Iterating over a `set` is less efficient than iterating over a sequence
type, such as `list` or `tuple`.

## Example

```python
for number in {1, 2, 3}:
    ...
```

Use instead:

```python
for number in (1, 2, 3):
    ...
```

## References

- [Python documentation: `set`](https://docs.python.org/3/library/stdtypes.html#set)
