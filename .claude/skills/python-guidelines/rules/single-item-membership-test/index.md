# single-item-membership-test (FURB171)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27single-item-membership-test%27%20OR%20FURB171)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Frefurb%2Frules%2Fsingle_item_membership_test.rs#L44)

Derived from the **[refurb](../#refurb-furb)** linter.

Fix is sometimes available.

## What it does

Checks for membership tests against single-item containers.

## Why is this bad?

Performing a membership test against a container (like a `list` or `set`)
with a single item is less readable and less efficient than comparing
against the item directly.

## Example

```python
1 in [1]
```

Use instead:

```python
1 == 1
```

## Fix safety

The fix is always marked as unsafe.

When the right-hand side is a string, this fix can change the behavior of your program.
This is because `c in "a"` is true both when `c` is `"a"` and when `c` is the empty string.

Additionally, converting `in`/`not in` against a single-item container to `==`/`!=` can
change runtime behavior: `in` may consider identity (e.g., `NaN`) and always
yields a `bool`.

Comments within the replacement range will also be removed.

## References

- [Python documentation: Comparisons](https://docs.python.org/3/reference/expressions.html#comparisons)
- [Python documentation: Membership test operations](https://docs.python.org/3/reference/expressions.html#membership-test-operations)
