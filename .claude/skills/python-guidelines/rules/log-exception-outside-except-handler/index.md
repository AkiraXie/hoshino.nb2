# log-exception-outside-except-handler (LOG004)

Preview (since [0.9.5](https://github.com/astral-sh/ruff/releases/tag/0.9.5)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27log-exception-outside-except-handler%27%20OR%20LOG004)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_logging%2Frules%2Flog_exception_outside_except_handler.rs#L71)

Derived from the **[flake8-logging](../#flake8-logging-log)** linter.

Fix is sometimes available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for `.exception()` logging calls outside of exception handlers.

## Why is this bad?

[The documentation](https://docs.python.org/3/library/logging.html#logging.exception) states:

> This function should only be called from an exception handler.

Calling `.exception()` outside of an exception handler
attaches `None` as exception information, leading to confusing messages:

```python
>>> logging.exception("example")
ERROR:root:example
NoneType: None
```

## Example

```python
import logging

logging.exception("Foobar")
```

Use instead:

```python
import logging

logging.error("Foobar")
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
        logging.exception("Foobar")  # LOG004 not raised (false negative)

handler()
```

## Fix safety

The fix, if available, will always be marked as unsafe, as it changes runtime behavior.

## Options

- [`lint.logger-objects`](../../settings/#lint_logger-objects)
