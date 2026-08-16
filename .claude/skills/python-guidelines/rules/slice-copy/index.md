# slice-copy (FURB145)

Preview (since [v0.0.290](https://github.com/astral-sh/ruff/releases/tag/v0.0.290)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27slice-copy%27%20OR%20FURB145)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Frefurb%2Frules%2Fslice_copy.rs#L43)

Derived from the **[refurb](../#refurb-furb)** linter.

Fix is sometimes available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for unbounded slice expressions to copy a list.

## Why is this bad?

The `list.copy` method is more readable and consistent with copying other
types.

## Known problems

This rule is prone to false negatives due to type inference limitations,
as it will only detect lists that are instantiated as literals or annotated
with a type annotation.

## Example

```python
a = [1, 2, 3]
b = a[:]
```

Use instead:

```python
a = [1, 2, 3]
b = a.copy()
```

## Fix safety

This rule's fix is marked as safe, unless the slice expression contains comments.

## References

- [Python documentation: Mutable Sequence Types](https://docs.python.org/3/library/stdtypes.html#mutable-sequence-types)
