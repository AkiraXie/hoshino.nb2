# quadratic-list-summation (RUF017)

Added in [v0.0.285](https://github.com/astral-sh/ruff/releases/tag/v0.0.285) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27quadratic-list-summation%27%20OR%20RUF017)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Fquadratic_list_summation.rs#L62)

Fix is always available.

## What it does

Checks for the use of `sum()` to flatten lists of lists, which has
quadratic complexity.

## Why is this bad?

The use of `sum()` to flatten lists of lists is quadratic in the number of
lists, as `sum()` creates a new list for each element in the summation.

Instead, consider using another method of flattening lists to avoid
quadratic complexity. The following methods are all linear in the number of
lists:

- `[*sublist for sublist in lists]` (Python 3.15+)
- `functools.reduce(operator.iadd, lists, [])`
- `list(itertools.chain.from_iterable(lists))`
- `[item for sublist in lists for item in sublist]`

When fixing relevant violations, Ruff uses the starred-list-comprehension
form on Python 3.15 and later. On older Python versions, Ruff falls back to
the `functools.reduce` form, which outperforms the other pre-3.15
alternatives in [microbenchmarks](https://github.com/astral-sh/ruff/issues/5073#issuecomment-1591836349).

## Example

```python
lists = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
joined = sum(lists, [])
```

Use instead:

```python
lists = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
joined = [*sublist for sublist in lists]
```

## Fix safety

This fix is always marked as unsafe because the replacement may accept any
iterable where `sum` previously required lists. On Python 3.15 and later,
Ruff uses iterable unpacking within a list comprehension; on older Python
versions, Ruff uses `operator.iadd`. In both cases, code that previously
raised an error may silently succeed. Moreover, the fix could remove
comments from the original code.

## References

- [*How Not to Flatten a List of Lists in Python*](https://mathieularose.com/how-not-to-flatten-a-list-of-lists-in-python)
- [*How do I make a flat list out of a list of lists?*](https://stackoverflow.com/questions/952914/how-do-i-make-a-flat-list-out-of-a-list-of-lists/953097#953097)
