# undocumented-public-nested-class (D106)

Added in [v0.0.70](https://github.com/astral-sh/ruff/releases/tag/v0.0.70) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27undocumented-public-nested-class%27%20OR%20D106)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpydocstyle%2Frules%2Fnot_missing.rs#L504)

Derived from the **[pydocstyle](../#pydocstyle-d)** linter.

## What it does

Checks for undocumented public class definitions, for nested classes.

## Why is this bad?

Public classes should be documented via docstrings to outline their
purpose and behavior.

Nested classes do not inherit the docstring of their enclosing class, so
they should have their own docstrings.

If the codebase adheres to a standard format for class docstrings, follow
that format for consistency.

## Example

```python
class Foo:
    """Class Foo."""

    class Bar: ...

bar = Foo.Bar()
bar.__doc__  # None
```

Use instead:

```python
class Foo:
    """Class Foo."""

    class Bar:
        """Class Bar."""

bar = Foo.Bar()
bar.__doc__  # "Class Bar."
```

## Options

- [`lint.pydocstyle.ignore-decorators`](../../settings/#lint_pydocstyle_ignore-decorators)

## References

- [PEP 257 – Docstring Conventions](https://peps.python.org/pep-0257/)
- [PEP 287 – reStructuredText Docstring Format](https://peps.python.org/pep-0287/)
- [NumPy Style Guide](https://numpydoc.readthedocs.io/en/latest/format.html)
- [Google Style Python Docstrings](https://google.github.io/styleguide/pyguide.html#s3.8-comments-and-docstrings)
