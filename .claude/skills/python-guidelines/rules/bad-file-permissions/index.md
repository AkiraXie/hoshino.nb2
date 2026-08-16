# bad-file-permissions (S103)

Added in [v0.0.211](https://github.com/astral-sh/ruff/releases/tag/v0.0.211) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27bad-file-permissions%27%20OR%20S103)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_bandit%2Frules%2Fbad_file_permissions.rs#L44)

Derived from the **[flake8-bandit](../#flake8-bandit-s)** linter.

## What it does

Checks for files with overly permissive permissions.

## Why is this bad?

Overly permissive file permissions may allow unintended access and
arbitrary code execution.

## Example

```python
import os

os.chmod("/etc/secrets.txt", 0o666)  # rw-rw-rw-
```

Use instead:

```python
import os

os.chmod("/etc/secrets.txt", 0o600)  # rw-------
```

## Preview

When [preview](https://docs.astral.sh/ruff/preview/) is enabled, the set of bits treated as dangerous matches
upstream Bandit (`0o33`): `S_IWOTH`, `S_IXOTH`, `S_IWGRP`, and `S_IXGRP`.
Outside preview, only `S_IWOTH` and `S_IXGRP` are flagged.

## References

- [Python documentation: `os.chmod`](https://docs.python.org/3/library/os.html#os.chmod)
- [Python documentation: `stat`](https://docs.python.org/3/library/stat.html)
- [Common Weakness Enumeration: CWE-732](https://cwe.mitre.org/data/definitions/732.html)
