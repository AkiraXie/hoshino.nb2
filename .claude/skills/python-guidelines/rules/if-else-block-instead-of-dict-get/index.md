# if-else-block-instead-of-dict-get (SIM401)

Added in [v0.0.219](https://github.com/astral-sh/ruff/releases/tag/v0.0.219) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27if-else-block-instead-of-dict-get%27%20OR%20SIM401)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_simplify%2Frules%2Fif_else_block_instead_of_dict_get.rs#L63)

Derived from the **[flake8-simplify](../#flake8-simplify-sim)** linter.

Fix is sometimes available.

## What it does

Checks for `if` statements that can be replaced with `dict.get` calls.

## Why is this bad?

`dict.get()` calls can be used to replace `if` statements that assign a
value to a variable in both branches, falling back to a default value if
the key is not found. When possible, using `dict.get` is more concise and
more idiomatic.

Under [preview mode](https://docs.astral.sh/ruff/preview), this rule will
also suggest replacing `if`-`else` *expressions* with `dict.get` calls.

## Example

```python
foo = {}
if "bar" in foo:
    value = foo["bar"]
else:
    value = 0
```

Use instead:

```python
foo = {}
value = foo.get("bar", 0)
```

If preview mode is enabled:

```python
value = foo["bar"] if "bar" in foo else 0
```

Use instead:

```python
value = foo.get("bar", 0)
```

## Options

The rule will avoid flagging cases where using the resulting `dict.get` call would exceed the
configured line length, as determined by these options:

- [`lint.pycodestyle.max-line-length`](../../settings/#lint_pycodestyle_max-line-length)
- [`indent-width`](../../settings/#indent-width)

## References

- [Python documentation: Mapping Types](https://docs.python.org/3/library/stdtypes.html#mapping-types-dict)
