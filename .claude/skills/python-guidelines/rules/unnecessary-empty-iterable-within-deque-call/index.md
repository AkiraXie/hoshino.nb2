# unnecessary-empty-iterable-within-deque-call (RUF037)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27unnecessary-empty-iterable-within-deque-call%27%20OR%20RUF037)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Funnecessary_literal_within_deque_call.rs#L48)

Fix is sometimes available.

## What it does

Checks for use of `collections.deque` with an empty iterable as the first argument.

## Why is this bad?

It's unnecessary to use an empty literal as a deque's iterable, since this is already the default behavior.

## Example

```python
from collections import deque

queue = deque(set())
queue = deque([], 10)
```

Use instead:

```python
from collections import deque

queue = deque()
queue = deque(maxlen=10)
```

## Fix safety

The fix is marked as unsafe whenever it would delete comments present in the `deque` call or if
there are unrecognized arguments other than `iterable` and `maxlen`.

## Fix availability

This rule's fix is unavailable if any starred arguments are present after the initial iterable.

## References

- [Python documentation: `collections.deque`](https://docs.python.org/3/library/collections.html#collections.deque)
