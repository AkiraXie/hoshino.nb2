# del-attr-with-constant (B043)

Preview (since [0.15.6](https://github.com/astral-sh/ruff/releases/tag/0.15.6)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27del-attr-with-constant%27%20OR%20B043)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_bugbear%2Frules%2Fdelattr_with_constant.rs#L46)

Derived from the **[flake8-bugbear](../#flake8-bugbear-b)** linter.

Fix is always available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for uses of `delattr` that take a constant attribute value as an
argument (e.g., `delattr(obj, "foo")`).

## Why is this bad?

`delattr` is used to delete attributes dynamically. If the attribute is
defined as a constant, it is no safer than a typical property deletion.
When possible, prefer `del` statements over `delattr` calls, as the
former is more concise and idiomatic.

## Example

```python
delattr(obj, "foo")
```

Use instead:

```python
del obj.foo
```

## Fix safety

The fix is marked as unsafe for attribute names that are not in NFKC
(Normalization Form KC) normalization. Python normalizes identifiers using
NFKC when using attribute access syntax (e.g., `del obj.attr`), but does
not normalize string arguments passed to `delattr`. Rewriting
`delattr(obj, "ſ")` to `del obj.ſ` would be interpreted as `del obj.s`
at runtime, changing behavior.

Additionally, the fix is marked as unsafe if the expression contains
comments, as the replacement may remove comments attached to the original
`delattr` call.

## References

- [Python documentation: `delattr`](https://docs.python.org/3/library/functions.html#delattr)
