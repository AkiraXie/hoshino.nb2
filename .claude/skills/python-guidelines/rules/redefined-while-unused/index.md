# redefined-while-unused (F811)

Added in [v0.0.171](https://github.com/astral-sh/ruff/releases/tag/v0.0.171) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27redefined-while-unused%27%20OR%20F811)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyflakes%2Frules%2Fredefined_while_unused.rs#L49)

Derived from the **[Pyflakes](../#pyflakes-f)** linter.

Fix is sometimes available.

## What it does

Checks for variable definitions that redefine (or "shadow") unused
variables.

## Why is this bad?

Redefinitions of unused names are unnecessary and often indicative of a
mistake.

## Example

```python
import foo
import bar
import foo  # Redefinition of unused `foo` from line 1
```

Use instead:

```python
import foo
import bar
```

## Preview

When [preview](https://docs.astral.sh/ruff/preview/) is enabled, this rule also flags annotated variable
redeclarations. For example, `bar: int = 1` followed by `bar: int = 2`
will be flagged as a redefinition of an unused variable, whereas plain
reassignments like `bar = 1` followed by `bar = 2` remain unflagged.

## Options

This rule ignores dummy variables, as determined by:

- [`lint.dummy-variable-rgx`](../../settings/#lint_dummy-variable-rgx)
