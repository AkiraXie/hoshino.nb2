# subprocess-run-without-check (PLW1510)

Added in [v0.0.285](https://github.com/astral-sh/ruff/releases/tag/v0.0.285) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27subprocess-run-without-check%27%20OR%20PLW1510)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fsubprocess_run_without_check.rs#L51)

Derived from the **[Pylint](../#pylint-pl)** linter.

Fix is sometimes available.

## What it does

Checks for uses of `subprocess.run` without an explicit `check` argument.

## Why is this bad?

By default, `subprocess.run` does not check the return code of the process
it runs. This can lead to silent failures.

Instead, consider using `check=True` to raise an exception if the process
fails, or set `check=False` explicitly to mark the behavior as intentional.

## Example

```python
import subprocess

subprocess.run(["ls", "nonexistent"])  # No exception raised.
```

Use instead:

```python
import subprocess

subprocess.run(["ls", "nonexistent"], check=True)  # Raises exception.
```

Or:

```python
import subprocess

subprocess.run(["ls", "nonexistent"], check=False)  # Explicitly no check.
```

## Fix safety

This rule's fix is marked as display-only because it's not clear whether the
potential exception was meant to be ignored by setting `check=False` or if
the author simply forgot to include `check=True`. The fix adds
`check=False`, making the existing behavior explicit but possibly masking
the original intention.

## References

- [Python documentation: `subprocess.run`](https://docs.python.org/3/library/subprocess.html#subprocess.run)
