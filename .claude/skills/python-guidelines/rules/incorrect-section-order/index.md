# incorrect-section-order (D420)

Preview (since [0.15.3](https://github.com/astral-sh/ruff/releases/tag/0.15.3)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27incorrect-section-order%27%20OR%20D420)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpydocstyle%2Frules%2Fsections.rs#L1430)

Derived from the **[pydocstyle](../#pydocstyle-d)** linter.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for docstring sections that appear out of order.

## Why is this bad?

Docstring sections should follow the canonical ordering specified by the
docstring convention (NumPy or Google). Consistent ordering makes
docstrings easier to read and navigate.

For the NumPy convention, all sections have a prescribed order per the
numpydoc style guide. For the Google convention, only the relative ordering
of `Args`, `Returns`/`Yields`, and `Raises` is enforced; all other sections
are unordered.

## Example

Given `lint.pydocstyle.convention = "numpy"`:

```python
def func() -> int:
    """Summary.

    Notes
    -----
    Some notes.

    Returns
    -------
    int
    """
```

Use instead:

```python
def func() -> int:
    """Summary.

    Returns
    -------
    int

    Notes
    -----
    Some notes.
    """
```

Given `lint.pydocstyle.convention = "google"`:

```python
def func(x: int) -> int:
    """Summary.

    Returns:
        int

    Args:
        x: Description.
    """
```

Use instead:

```python
def func(x: int) -> int:
    """Summary.

    Args:
        x: Description.

    Returns:
        int
    """
```

## Options

- [`lint.pydocstyle.convention`](../../settings/#lint_pydocstyle_convention)

## References

- [NumPy docstring standard](https://numpydoc.readthedocs.io/en/latest/format.html)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#383-functions-and-methods)
