# unnecessary-assign-before-yield (RUF070)

Preview (since [0.15.3](https://github.com/astral-sh/ruff/releases/tag/0.15.3)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27unnecessary-assign-before-yield%27%20OR%20RUF070)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Funnecessary_assign_before_yield.rs#L42)

Fix is always available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for variable assignments that immediately precede a `yield` (or
`yield from`) of the assigned variable, where the variable is not
referenced anywhere else.

## Why is this bad?

The variable assignment is not necessary, as the value can be yielded
directly.

## Example

```python
def gen():
    x = 1
    yield x
```

Use instead:

```python
def gen():
    yield 1
```

## Fix safety

This fix is always marked as unsafe because removing the intermediate
variable assignment changes the local variable bindings visible to
`locals()` and debuggers when the generator is suspended at the `yield`.
