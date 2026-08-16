# missing-return-type-class-method (ANN206)

Added in [v0.0.105](https://github.com/astral-sh/ruff/releases/tag/v0.0.105) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27missing-return-type-class-method%27%20OR%20ANN206)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_annotations%2Frules%2Fdefinition.rs#L462)

Derived from the **[flake8-annotations](../#flake8-annotations-ann)** linter.

Fix is sometimes available.

## What it does

Checks that class methods have return type annotations.

## Why is this bad?

Type annotations are a good way to document the return types of functions. They also
help catch bugs, when used alongside a type checker, by ensuring that the types of
any returned values, and the types expected by callers, match expectation.

## Example

```python
class Foo:
    @classmethod
    def bar(cls):
        return 1
```

Use instead:

```python
class Foo:
    @classmethod
    def bar(cls) -> int:
        return 1
```

## Options

- [`lint.flake8-annotations.suppress-none-returning`](../../settings/#lint_flake8-annotations_suppress-none-returning)
