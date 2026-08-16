# lru-cache-with-maxsize-none (UP033)

Added in [v0.0.225](https://github.com/astral-sh/ruff/releases/tag/v0.0.225) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27lru-cache-with-maxsize-none%27%20OR%20UP033)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyupgrade%2Frules%2Flru_cache_with_maxsize_none.rs#L47)

Derived from the **[pyupgrade](../#pyupgrade-up)** linter.

Fix is always available.

## What it does

Checks for uses of `functools.lru_cache` that set `maxsize=None`.

## Why is this bad?

Since Python 3.9, `functools.cache` can be used as a drop-in replacement
for `functools.lru_cache(maxsize=None)`. When possible, prefer
`functools.cache` as it is more readable and idiomatic.

## Example

```python
import functools

@functools.lru_cache(maxsize=None)
def foo(): ...
```

Use instead:

```python
import functools

@functools.cache
def foo(): ...
```

## Options

- [`target-version`](../../settings/#target-version)

## Fix safety

This rule's fix is marked as safe, unless the expression contains comments.

## References

- [Python documentation: `@functools.cache`](https://docs.python.org/3/library/functools.html#functools.cache)
