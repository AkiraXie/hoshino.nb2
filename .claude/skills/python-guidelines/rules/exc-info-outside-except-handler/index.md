# exc-info-outside-except-handler (LOG014)

Added in [0.12.0](https://github.com/astral-sh/ruff/releases/tag/0.12.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27exc-info-outside-except-handler%27%20OR%20LOG014)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_logging%2Frules%2Fexc_info_outside_except_handler.rs#L71)

Derived from the **[flake8-logging](../#flake8-logging-log)** linter.

Fix is sometimes available.

## What it does

Checks for logging calls with `exc_info=` outside exception handlers.

## Why is this bad?

Using `exc_info=True` outside of an exception handler
attaches `None` as the exception information, leading to confusing messages:

```python
>>> logging.warning("Uh oh", exc_info=True)
WARNING:root:Uh oh
NoneType: None
```

## Example

```python
import logging

logging.warning("Foobar", exc_info=True)
```

Use instead:

```python
import logging

logging.warning("Foobar")
```

## Known limitations

This rule checks whether a call is *defined* inside an exception handler, not
whether it *executes* inside one. A function defined in an `except` block but
called outside of it will not be flagged, despite the fact that the call may
not have access to an active exception at runtime:

```python
import logging

try:
    raise ValueError()
except Exception:

    def handler():
        logging.error("Foobar", exc_info=True)  # LOG014 not raised (false negative)

handler()
```

## Fix safety

The fix is always marked as unsafe, as it changes runtime behavior.

## Options

- [`lint.logger-objects`](../../settings/#lint_logger-objects)
