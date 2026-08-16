# reimplemented-starmap (FURB140)

Preview (since [v0.0.291](https://github.com/astral-sh/ruff/releases/tag/v0.0.291)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27reimplemented-starmap%27%20OR%20FURB140)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Frefurb%2Frules%2Freimplemented_starmap.rs#L52)

Derived from the **[refurb](../#refurb-furb)** linter.

Fix is sometimes available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for generator expressions, list and set comprehensions that can
be replaced with `itertools.starmap`.

## Why is this bad?

When unpacking values from iterators to pass them directly to
a function, prefer `itertools.starmap`.

Using `itertools.starmap` is more concise and readable. Furthermore, it is
more efficient than generator expressions, and in some versions of Python,
it is more efficient than comprehensions.

## Known problems

Since Python 3.12, `itertools.starmap` is less efficient than
comprehensions ([#7771](https://github.com/astral-sh/ruff/issues/7771)). This is due to [PEP 709](https://peps.python.org/pep-0709/), which made
comprehensions faster.

## Example

```python
all(predicate(a, b) for a, b in some_iterable)
```

Use instead:

```python
from itertools import starmap

all(starmap(predicate, some_iterable))
```

## Fix safety

This rule's fix is marked as safe, unless the expression contains comments.

## References

- [Python documentation: `itertools.starmap`](https://docs.python.org/3/library/itertools.html#itertools.starmap)
