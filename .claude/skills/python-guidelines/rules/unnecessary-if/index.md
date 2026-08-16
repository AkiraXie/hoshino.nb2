# unnecessary-if (RUF050)

Preview (since [0.15.8](https://github.com/astral-sh/ruff/releases/tag/0.15.8)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27unnecessary-if%27%20OR%20RUF050)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Funnecessary_if.rs#L61)

Fix is always available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for `if` statements (without `elif` or `else` branches) where the
body contains only `pass` or `...`

## Why is this bad?

An `if` statement with an empty body either does nothing (when the
condition is side-effect-free) or could be replaced with just the
condition expression (when it has side effects). This pattern commonly
arises when auto-fixers remove unused imports from conditional blocks
(e.g., version-dependent imports), leaving behind an empty skeleton.

## Example

```python
import sys

if sys.version_info >= (3, 11):
    pass
```

Use instead:

```python
import sys
```

## Fix safety

When the condition is side-effect-free, the fix removes the entire `if`
statement.

When the condition has side effects (e.g., a function call), the fix
replaces the `if` statement with just the condition as an expression
statement, preserving the side effects.

Note: conditions consisting solely of a name expression (like
`if x: pass`) are treated as side-effect-free, even though `if x`
implicitly calls `x.__bool__()` (or `x.__len__()`), which could have
side effects if overridden. In practice this is very rare, but if you
rely on this behavior, suppress the diagnostic with `# noqa: RUF050`.

## Related rules

- [`needless-else (RUF047)`][needless-else (RUF047)]: Detects empty `else` clauses. For `if`/`else`
  statements where all branches are empty, `RUF047` first removes the empty
  `else`, and then this rule catches the remaining empty `if`.
- [`empty-type-checking-block (TC005)`][empty-type-checking-block (TC005)]: Detects empty `if TYPE_CHECKING`
  blocks specifically.
