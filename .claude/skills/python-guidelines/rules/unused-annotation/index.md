# unused-annotation (F842)

Added in [v0.0.172](https://github.com/astral-sh/ruff/releases/tag/v0.0.172) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27unused-annotation%27%20OR%20F842)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyflakes%2Frules%2Funused_annotation.rs#L29)

Derived from the **[Pyflakes](../#pyflakes-f)** linter.

## What it does

Checks for local variables that are annotated but never used.

## Why is this bad?

Annotations are used to provide type hints to static type checkers. If a
variable is annotated but never used, the annotation is unnecessary.

## Example

```python
def foo():
    bar: int
```

## Options

This rule ignores dummy variables, as determined by:

- [`lint.dummy-variable-rgx`](../../settings/#lint_dummy-variable-rgx)

## References

- [PEP 484 – Type Hints](https://peps.python.org/pep-0484/)
