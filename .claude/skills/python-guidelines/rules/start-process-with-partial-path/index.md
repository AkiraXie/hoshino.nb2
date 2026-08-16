# start-process-with-partial-path (S607)

Added in [v0.0.262](https://github.com/astral-sh/ruff/releases/tag/v0.0.262) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27start-process-with-partial-path%27%20OR%20S607)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_bandit%2Frules%2Fshell_injection.rs#L252)

Derived from the **[flake8-bandit](../#flake8-bandit-s)** linter.

## What it does

Checks for the starting of a process with a partial executable path.

## Why is this bad?

Starting a process with a partial executable path can allow attackers to
execute an arbitrary executable by adjusting the `PATH` environment variable.
Consider using a full path to the executable instead.

## Example

```python
import subprocess

subprocess.Popen(["ruff", "check", "file.py"])
```

Use instead:

```python
import subprocess

subprocess.Popen(["/usr/bin/ruff", "check", "file.py"])
```

## References

- [Python documentation: `subprocess.Popen()`](https://docs.python.org/3/library/subprocess.html#subprocess.Popen)
- [Common Weakness Enumeration: CWE-426](https://cwe.mitre.org/data/definitions/426.html)
