# undocumented-public-package (D104)

Added in [v0.0.70](https://github.com/astral-sh/ruff/releases/tag/v0.0.70) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27undocumented-public-package%27%20OR%20D104)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpydocstyle%2Frules%2Fnot_missing.rs#L386)

Derived from the **[pydocstyle](../#pydocstyle-d)** linter.

## What it does

Checks for undocumented public package definitions.

## Why is this bad?

Public packages should be documented via docstrings to outline their
purpose and contents.

Generally, package docstrings should list the modules and subpackages that
are exported by the package.

If the codebase adheres to a standard format for package docstrings, follow
that format for consistency.

## Example

```python
__all__ = ["Player", "Game"]
```

Use instead:

```python
"""Game and player management package.

This package provides classes for managing players and games.
"""

__all__ = ["player", "game"]
```

## Options

- [`lint.pydocstyle.ignore-decorators`](../../settings/#lint_pydocstyle_ignore-decorators)

## References

- [PEP 257 – Docstring Conventions](https://peps.python.org/pep-0257/)
- [PEP 287 – reStructuredText Docstring Format](https://peps.python.org/pep-0287/)
- [NumPy Style Guide](https://numpydoc.readthedocs.io/en/latest/format.html)
- [Google Style Python Docstrings](https://google.github.io/styleguide/pyguide.html#s3.8-comments-and-docstrings)
