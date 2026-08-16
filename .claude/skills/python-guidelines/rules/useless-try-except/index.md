# useless-try-except (TRY203)

Added in [0.7.0](https://github.com/astral-sh/ruff/releases/tag/0.7.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27useless-try-except%27%20OR%20TRY203)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Ftryceratops%2Frules%2Fuseless_try_except.rs#L31)

Derived from the **[tryceratops](../#tryceratops-try)** linter.

## What it does

Checks for immediate uses of `raise` within exception handlers.

## Why is this bad?

Capturing an exception, only to immediately reraise it, has no effect.
Instead, remove the error-handling code and let the exception propagate
upwards without the unnecessary `try`-`except` block.

## Example

```python
def foo():
    try:
        bar()
    except NotImplementedError:
        raise
```

Use instead:

```python
def foo():
    bar()
```
