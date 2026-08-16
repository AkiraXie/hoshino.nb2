# unused-private-type-alias (PYI047)

Added in [v0.0.281](https://github.com/astral-sh/ruff/releases/tag/v0.0.281) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27unused-private-type-alias%27%20OR%20PYI047)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_pyi%2Frules%2Funused_private_type_definition.rs#L128)

Derived from the **[flake8-pyi](../#flake8-pyi-pyi)** linter.

## What it does

Checks for the presence of unused private type aliases.

## Why is this bad?

A private type alias that is defined but not used is likely a
mistake. It should either be used, made public, or removed to avoid
confusion.

## Example

```python
import typing

_UnusedTypeAlias: typing.TypeAlias = int
```

Use instead:

```python
import typing

_UsedTypeAlias: typing.TypeAlias = int

def func(arg: _UsedTypeAlias) -> _UsedTypeAlias: ...
```
