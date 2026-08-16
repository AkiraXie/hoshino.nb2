# no-explicit-stacklevel (B028)

Added in [v0.0.257](https://github.com/astral-sh/ruff/releases/tag/v0.0.257) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27no-explicit-stacklevel%27%20OR%20B028)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_bugbear%2Frules%2Fno_explicit_stacklevel.rs#L48)

Derived from the **[flake8-bugbear](../#flake8-bugbear-b)** linter.

Fix is always available.

## What it does

Checks for `warnings.warn` calls without an explicit `stacklevel` keyword
argument.

## Why is this bad?

The `warnings.warn` method uses a `stacklevel` of 1 by default, which
will output a stack frame of the line on which the "warn" method
is called. Setting it to a higher number will output a stack frame
from higher up the stack.

It's recommended to use a `stacklevel` of 2 or higher, to give the caller
more context about the warning.

In Python 3.12 and higher, one may also use `skip_file_prefixes` to specify
which file prefixes are ignored when counting the stack level. This implicitly overrides the `stacklevel` to be
at least 2, according to the [Python documentation](https://docs.python.org/3/library/warnings.html#warnings.warn).

## Example

```python
import warnings

warnings.warn("This is a warning")
```

Use instead:

```python
import warnings

warnings.warn("This is a warning", stacklevel=2)
```

## Fix safety

This rule's fix is marked as unsafe because it changes
the behavior of the code. Moreover, the fix will assign
a stacklevel of 2, while the user may wish to assign a
higher stacklevel to address the diagnostic.

## References

- [Python documentation: `warnings.warn`](https://docs.python.org/3/library/warnings.html#warnings.warn)
