# os-path-commonprefix (RUF071)

Preview (since [0.15.6](https://github.com/astral-sh/ruff/releases/tag/0.15.6)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27os-path-commonprefix%27%20OR%20RUF071)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Fos_path_commonprefix.rs#L69)

Fix is sometimes available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for uses of `os.path.commonprefix`.

## Why is this bad?

`os.path.commonprefix` performs a character-by-character string
comparison rather than comparing path components. This leads to
incorrect results when paths share a common string prefix that
is not a valid path component.

`os.path.commonpath` correctly compares path components.

`os.path.commonprefix` is deprecated as of Python 3.15.

## Example

```python
import os

# Returns "/usr/l" — not a valid directory!
os.path.commonprefix(["/usr/lib", "/usr/local/lib"])
```

Use instead:

```python
import os

# Returns "/usr" — correct common path
os.path.commonpath(["/usr/lib", "/usr/local/lib"])
```

## Fix safety

This fix is marked as unsafe because `os.path.commonprefix` and
`os.path.commonpath` have different semantics:

- `commonprefix` performs a character-by-character string comparison
  and returns the longest common string prefix.
- `commonpath` compares path components and returns the longest common
  path prefix.

If you are intentionally using `commonprefix` for non-path string
comparisons (e.g., finding a common prefix among arbitrary strings
like version numbers or identifiers), see the
[error suppression](https://docs.astral.sh/ruff/linter/#error-suppression)
documentation for ways to disable this rule.

For example:

```python
import os

# commonprefix works on non-path strings
os.path.commonprefix(["12345", "12378"])  # "123"
os.path.commonpath(["12345", "12378"])  # ""
```

## References

- [Python documentation: `os.path.commonprefix`](https://docs.python.org/3/library/os.path.html#os.path.commonprefix)
- [Python documentation: `os.path.commonpath`](https://docs.python.org/3/library/os.path.html#os.path.commonpath)
- [Why `os.path.commonprefix` is deprecated](https://sethmlarson.dev/deprecate-confusing-apis-like-os-path-commonprefix)
- [CPython deprecation issue](https://github.com/python/cpython/issues/144347)
