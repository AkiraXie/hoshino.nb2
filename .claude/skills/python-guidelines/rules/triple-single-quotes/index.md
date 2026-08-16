# triple-single-quotes (D300)

Added in [v0.0.69](https://github.com/astral-sh/ruff/releases/tag/v0.0.69) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27triple-single-quotes%27%20OR%20D300)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpydocstyle%2Frules%2Ftriple_quotes.rs#L49)

Derived from the **[pydocstyle](../#pydocstyle-d)** linter.

Fix is sometimes available.

## What it does

Checks for docstrings that don't use `"""triple double quotes"""`.

## Why is this bad?

[PEP 257](https://peps.python.org/pep-0257/#what-is-a-docstring) recommends
the use of `"""triple double quotes"""` for docstrings, to ensure
consistency.

## Example

```python
def kos_root():
    '''Return the pathname of the KOS root directory.'''

def kos_branch():
    'Return the branch name.'
```

Use instead:

```python
def kos_root():
    """Return the pathname of the KOS root directory."""

def kos_branch():
    """Return the branch name."""
```

## Formatter compatibility

We recommend against using this rule alongside the [formatter](https://docs.astral.sh/ruff/formatter/). The
formatter enforces consistent quotes, making the rule redundant.

## Options

- [`lint.pydocstyle.ignore-decorators`](../../settings/#lint_pydocstyle_ignore-decorators)

## References

- [PEP 257 – Docstring Conventions](https://peps.python.org/pep-0257/)
- [NumPy Style Guide](https://numpydoc.readthedocs.io/en/latest/format.html)
- [Google Python Style Guide - Docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
