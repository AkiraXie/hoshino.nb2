# missing-maxsplit-arg (PLC0207)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27missing-maxsplit-arg%27%20OR%20PLC0207)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fmissing_maxsplit_arg.rs#L44)

Derived from the **[Pylint](../#pylint-pl)** linter.

Fix is always available.

## What it does

Checks for access to the first or last element of `str.split()` or `str.rsplit()` without a
`maxsplit=1` argument.

## Why is this bad?

Calling `str.split()` or `str.rsplit()` without passing `maxsplit=1` splits on every delimiter in the
string. When accessing only the first or last element of the result, it
would be more efficient to split only once.

## Example

```python
url = "www.example.com"
prefix = url.split(".")[0]
```

Use instead:

```python
url = "www.example.com"
prefix = url.split(".", maxsplit=1)[0]
```

To access the last element, use `str.rsplit()` instead of `str.split()`:

```python
url = "www.example.com"
suffix = url.rsplit(".", maxsplit=1)[-1]
```

## Fix Safety

This rule's fix is marked as unsafe for `split()`/`rsplit()` calls that contain `*args` or
`**kwargs` arguments, as adding a `maxsplit` argument to such a call may lead to duplicate
arguments.
