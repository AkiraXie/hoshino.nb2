# missing-type-kwargs (ANN003)

Added in [v0.0.105](https://github.com/astral-sh/ruff/releases/tag/v0.0.105) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27missing-type-kwargs%27%20OR%20ANN003)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_annotations%2Frules%2Fdefinition.rs#L112)

Derived from the **[flake8-annotations](../#flake8-annotations-ann)** linter.

## What it does

Checks that function `**kwargs` arguments have type annotations.

## Why is this bad?

Type annotations are a good way to document the types of function arguments. They also
help catch bugs, when used alongside a type checker, by ensuring that the types of
any provided arguments match expectation.

## Example

```python
def foo(**kwargs): ...
```

Use instead:

```python
def foo(**kwargs: int): ...
```

## Options

- [`lint.flake8-annotations.suppress-dummy-args`](../../settings/#lint_flake8-annotations_suppress-dummy-args)
