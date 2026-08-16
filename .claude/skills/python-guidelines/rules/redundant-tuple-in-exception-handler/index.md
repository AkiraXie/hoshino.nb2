# redundant-tuple-in-exception-handler (B013)

Added in [v0.0.89](https://github.com/astral-sh/ruff/releases/tag/v0.0.89) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27redundant-tuple-in-exception-handler%27%20OR%20B013)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_bugbear%2Frules%2Fredundant_tuple_in_exception_handler.rs#L42)

Derived from the **[flake8-bugbear](../#flake8-bugbear-b)** linter.

Fix is always available.

## What it does

Checks for single-element tuples in exception handlers (e.g.,
`except (ValueError,):`).

Note: Single-element tuples consisting of a starred expression
are allowed.

## Why is this bad?

A tuple with a single element can be more concisely and idiomatically
expressed as a single value.

## Example

```python
try:
    ...
except (ValueError,):
    ...
```

Use instead:

```python
try:
    ...
except ValueError:
    ...
```

## Fix safety

This rule's fix is marked as safe, unless the exception handler contains comments.

## References

- [Python documentation: `except` clause](https://docs.python.org/3/reference/compound_stmts.html#except-clause)
