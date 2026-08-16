# raise-without-from-inside-except (B904)

Added in [v0.0.138](https://github.com/astral-sh/ruff/releases/tag/v0.0.138) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27raise-without-from-inside-except%27%20OR%20B904)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_bugbear%2Frules%2Fraise_without_from_inside_except.rs#L51)

Derived from the **[flake8-bugbear](../#flake8-bugbear-b)** linter.

## What it does

Checks for `raise` statements in exception handlers that lack a `from`
clause.

## Why is this bad?

In Python, `raise` can be used with or without an exception from which the
current exception is derived. This is known as exception chaining. When
printing the stack trace, chained exceptions are displayed in such a way
so as make it easier to trace the exception back to its root cause.

When raising a new exception from within an `except` clause, it's recommended to
include a `from` clause to explicitly set the exception's cause. Without it,
Python will implicitly chain from the current exception (setting `__context__`),
but the `__cause__` attribute won't be set, which may make debugging slightly
more difficult.

## Example

```python
try:
    ...
except FileNotFoundError:
    if ...:
        raise RuntimeError("...")
    else:
        raise UserWarning("...")
```

Use instead:

```python
try:
    ...
except FileNotFoundError as exc:
    if ...:
        raise RuntimeError("...") from None
    else:
        raise UserWarning("...") from exc
```

## References

- [Python documentation: `raise` statement](https://docs.python.org/3/reference/simple_stmts.html#the-raise-statement)
