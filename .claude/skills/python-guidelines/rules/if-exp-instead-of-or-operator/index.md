# if-exp-instead-of-or-operator (FURB110)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27if-exp-instead-of-or-operator%27%20OR%20FURB110)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Frefurb%2Frules%2Fif_exp_instead_of_or_operator.rs#L44)

Derived from the **[refurb](../#refurb-furb)** linter.

Fix is sometimes available.

## What it does

Checks for ternary `if` expressions that can be replaced with the `or`
operator.

## Why is this bad?

Ternary `if` expressions are more verbose than `or` expressions while
providing the same functionality.

## Example

```python
x, y = 1, 2

z = x if x else y
```

Use instead:

```python
x, y = 1, 2

z = x or y
```

## Fix safety

This rule's fix is marked as unsafe in the event that the body of the
`if` expression contains side effects or comments.

For example, `foo` will be called twice in `foo() if foo() else bar()`
(assuming `foo()` returns a truthy value), but only once in
`foo() or bar()`.
