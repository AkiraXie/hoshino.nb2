# property-with-parameters (PLR0206)

Added in [v0.0.153](https://github.com/astral-sh/ruff/releases/tag/v0.0.153) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27property-with-parameters%27%20OR%20PLR0206)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fproperty_with_parameters.rs#L41)

Derived from the **[Pylint](../#pylint-pl)** linter.

## What it does

Checks for property definitions that accept function parameters.

## Why is this bad?

Properties cannot be called with parameters.

If you need to pass parameters to a property, create a method with the
desired parameters and call that method instead.

## Example

```python
class Cat:
    @property
    def purr(self, volume): ...
```

Use instead:

```python
class Cat:
    @property
    def purr(self): ...

    def purr_volume(self, volume): ...
```

## Options

- [`lint.pydocstyle.property-decorators`](../../settings/#lint_pydocstyle_property-decorators)

## References

- [Python documentation: `property`](https://docs.python.org/3/library/functions.html#property)
