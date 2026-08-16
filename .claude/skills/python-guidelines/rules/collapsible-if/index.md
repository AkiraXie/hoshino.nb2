# collapsible-if (SIM102)

Added in [v0.0.211](https://github.com/astral-sh/ruff/releases/tag/v0.0.211) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27collapsible-if%27%20OR%20SIM102)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_simplify%2Frules%2Fcollapsible_if.rs#L65)

Derived from the **[flake8-simplify](../#flake8-simplify-sim)** linter.

Fix is sometimes available.

## What it does

Checks for nested `if` statements that can be collapsed into a single `if`
statement.

## Why is this bad?

Nesting `if` statements leads to deeper indentation and makes code harder to
read. Instead, combine the conditions into a single `if` statement with an
`and` operator.

## Example

```python
if foo:
    if bar:
        ...
```

Use instead:

```python
if foo and bar:
    ...
```

## Preview and Fix Safety

When [preview](https://docs.astral.sh/ruff/preview/) is enabled, the fix for this rule is considered
as safe. When [preview](https://docs.astral.sh/ruff/preview/) is not enabled, the fix is always
considered unsafe.

## Options

The rule will consult these two settings when deciding if a fix can be provided:

- [`lint.pycodestyle.max-line-length`](../../settings/#lint_pycodestyle_max-line-length)
- [`indent-width`](../../settings/#indent-width)

Lines that would exceed the configured line length will not be fixed automatically.

## References

- [Python documentation: The `if` statement](https://docs.python.org/3/reference/compound_stmts.html#the-if-statement)
- [Python documentation: Boolean operations](https://docs.python.org/3/reference/expressions.html#boolean-operations)
