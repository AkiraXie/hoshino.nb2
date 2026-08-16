# in-dict-keys (SIM118)

Added in [v0.0.176](https://github.com/astral-sh/ruff/releases/tag/v0.0.176) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27in-dict-keys%27%20OR%20SIM118)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_simplify%2Frules%2Fkey_in_dict.rs#L40)

Derived from the **[flake8-simplify](../#flake8-simplify-sim)** linter.

Fix is always available.

## What it does

Checks for key-existence checks against `dict.keys()` calls.

## Why is this bad?

When checking for the existence of a key in a given dictionary, using
`key in dict` is more readable and efficient than `key in dict.keys()`,
while having the same semantics.

## Example

```python
key in foo.keys()
```

Use instead:

```python
key in foo
```

## Fix safety

Given `key in obj.keys()`, `obj` *could* be a dictionary, or it could be
another type that defines a `.keys()` method. In the latter case, removing
the `.keys()` attribute could lead to a runtime error. The fix is marked
as safe when the type of `obj` is known to be a dictionary; otherwise, it
is marked as unsafe.

## References

- [Python documentation: Mapping Types](https://docs.python.org/3/library/stdtypes.html#mapping-types-dict)
