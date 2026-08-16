# empty-docstring (D419)

Added in [v0.0.68](https://github.com/astral-sh/ruff/releases/tag/v0.0.68) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27empty-docstring%27%20OR%20D419)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpydocstyle%2Frules%2Fnot_empty.rs#L35)

Derived from the **[pydocstyle](../#pydocstyle-d)** linter.

## What it does

Checks for empty docstrings.

## Why is this bad?

An empty docstring is indicative of incomplete documentation. It should either
be removed or replaced with a meaningful docstring.

## Example

```python
def average(values: list[float]) -> float:
    """"""
```

Use instead:

```python
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
```

## Options

- [`lint.pydocstyle.ignore-decorators`](../../settings/#lint_pydocstyle_ignore-decorators)

## References

- [PEP 257 – Docstring Conventions](https://peps.python.org/pep-0257/)
- [NumPy Style Guide](https://numpydoc.readthedocs.io/en/latest/format.html)
- [Google Python Style Guide - Docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
