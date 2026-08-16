# swap-with-temporary-variable (PLR1712)

Preview (since [0.15.3](https://github.com/astral-sh/ruff/releases/tag/0.15.3)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27swap-with-temporary-variable%27%20OR%20PLR1712)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fswap_with_temporary_variable.rs#L41)

Derived from the **[Pylint](../#pylint-pl)** linter.

Fix is sometimes available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for code that swaps two variables using a temporary variable.

## Why is this bad?

Variables can be swapped by using tuple unpacking instead of using a
temporary variable. That also makes the intention of the swapping logic
more clear.

## Example

```python
def function(x, y):
    if x > y:
        temp = x
        x = y
        y = temp
    assert x <= y
```

Use instead:

```python
def function(x, y):
    if x > y:
        x, y = y, x
    assert x <= y
```

## Fix safety

The rule's fix is marked as safe, unless the replacement range contains comments
that would be removed.
