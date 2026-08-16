# docstring-tab-indentation (D206)

Added in [v0.0.75](https://github.com/astral-sh/ruff/releases/tag/v0.0.75) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27docstring-tab-indentation%27%20OR%20D206)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpydocstyle%2Frules%2Findent.rs#L58)

Derived from the **[pydocstyle](../#pydocstyle-d)** linter.

## What it does

Checks for docstrings that are indented with tabs.

## Why is this bad?

[PEP 8](https://peps.python.org/pep-0008/#tabs-or-spaces) recommends using spaces over tabs for indentation.

## Example

```python
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.

    Sort the list in ascending order and return a copy of the result using the bubble
    sort algorithm.
    """
```

Use instead:

```python
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.

    Sort the list in ascending order and return a copy of the result using the bubble
    sort algorithm.
    """
```

## Formatter compatibility

We recommend against using this rule alongside the [formatter](https://docs.astral.sh/ruff/formatter). The
formatter enforces consistent indentation, making the rule redundant.

The rule is also incompatible with the [formatter](https://docs.astral.sh/ruff/formatter) when using
`format.indent-style="tab"`.

## Options

- [`lint.pydocstyle.ignore-decorators`](../../settings/#lint_pydocstyle_ignore-decorators)

## References

- [PEP 257 – Docstring Conventions](https://peps.python.org/pep-0257/)
- [NumPy Style Guide](https://numpydoc.readthedocs.io/en/latest/format.html)
- [Google Python Style Guide - Docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
