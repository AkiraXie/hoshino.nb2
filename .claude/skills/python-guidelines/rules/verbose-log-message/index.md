# verbose-log-message (TRY401)

Added in [v0.0.250](https://github.com/astral-sh/ruff/releases/tag/v0.0.250) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27verbose-log-message%27%20OR%20TRY401)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Ftryceratops%2Frules%2Fverbose_log_message.rs#L40)

Derived from the **[tryceratops](../#tryceratops-try)** linter.

## What it does

Checks for excessive logging of exception objects.

## Why is this bad?

When logging exceptions via `logging.exception`, the exception object
is logged automatically. Including the exception object in the log
message is redundant and can lead to excessive logging.

## Example

```python
try:
    ...
except ValueError as e:
    logger.exception(f"Found an error: {e}")
```

Use instead:

```python
try:
    ...
except ValueError:
    logger.exception("Found an error")
```

## Options

- [`lint.logger-objects`](../../settings/#lint_logger-objects)
