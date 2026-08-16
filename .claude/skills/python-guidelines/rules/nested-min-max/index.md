# nested-min-max (PLW3301)

Added in [v0.0.266](https://github.com/astral-sh/ruff/releases/tag/v0.0.266) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27nested-min-max%27%20OR%20PLW3301)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fnested_min_max.rs#L77)

Derived from the **[Pylint](../#pylint-pl)** linter.

Fix is sometimes available.

## What it does

Checks for nested `min` and `max` calls.

## Why is this bad?

Nested `min` and `max` calls can be flattened into a single call to improve
readability.

## Example

```python
minimum = min(1, 2, min(3, 4, 5))
maximum = max(1, 2, max(3, 4, 5))
diff = maximum - minimum
```

Use instead:

```python
minimum = min(1, 2, 3, 4, 5)
maximum = max(1, 2, 3, 4, 5)
diff = maximum - minimum
```

## Known issues

The resulting code may be slower and use more memory, especially for nested iterables. For
example, this code:

```python
iterable = range(3)
min(1, min(iterable))
```

will be fixed to:

```python
iterable = range(3)
min(1, *iterable)
```

At least on current versions of CPython, this allocates a collection for the whole iterable
before calling `min` and could cause performance regressions, at least for large iterables.

## Fix safety

This fix is always unsafe and may change the program's behavior for types without full
equivalence relations, such as float comparisons involving `NaN`.

```python
print(min(2.0, min(float("nan"), 1.0)))  # before fix: 2.0
print(min(2.0, float("nan"), 1.0))  # after fix: 1.0

print(max(1.0, max(float("nan"), 2.0)))  # before fix: 1.0
print(max(1.0, float("nan"), 2.0))  # after fix: 2.0
```

The fix will also remove any comments within the outer call.

## References

- [Python documentation: `min`](https://docs.python.org/3/library/functions.html#min)
- [Python documentation: `max`](https://docs.python.org/3/library/functions.html#max)
