# print (T201)

Added in [v0.0.57](https://github.com/astral-sh/ruff/releases/tag/v0.0.57) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27print%27%20OR%20T201)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_print%2Frules%2Fprint_call.rs#L55)

Derived from the **[flake8-print](../#flake8-print-t20)** linter.

Fix is sometimes available.

## What it does

Checks for `print` statements.

## Why is this bad?

`print` statements used for debugging should be omitted from production
code. They can lead the accidental inclusion of sensitive information in
logs, and are not configurable by clients, unlike `logging` statements.

`print` statements used to produce output as a part of a command-line
interface program are not typically a problem.

## Example

```python
def sum_less_than_four(a, b):
    print(f"Calling sum_less_than_four")
    return a + b < 4
```

The automatic fix will remove the print statement entirely:

```python
def sum_less_than_four(a, b):
    return a + b < 4
```

To keep the line for logging purposes, instead use something like:

```python
import logging

logger = logging.getLogger(__name__)

def sum_less_than_four(a, b):
    logger.debug("Calling sum_less_than_four")
    return a + b < 4

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
```

## Fix safety

This rule's fix is marked as unsafe, as it will remove `print` statements
that are used beyond debugging purposes.
