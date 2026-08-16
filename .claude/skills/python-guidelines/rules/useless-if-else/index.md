# useless-if-else (RUF034)

Added in [0.9.0](https://github.com/astral-sh/ruff/releases/tag/0.9.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27useless-if-else%27%20OR%20RUF034)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Fuseless_if_else.rs#L24)

## What it does

Checks for useless `if`-`else` conditions with identical arms.

## Why is this bad?

Useless `if`-`else` conditions add unnecessary complexity to the code without
providing any logical benefit. Assigning the value directly is clearer.

## Example

```python
foo = x if y else x
```

Use instead:

```python
foo = x
```
