# replace-str-enum (UP042)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27replace-str-enum%27%20OR%20UP042)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyupgrade%2Frules%2Freplace_str_enum.rs#L83)

Derived from the **[pyupgrade](../#pyupgrade-up)** linter.

Fix is sometimes available.

## What it does

Checks for classes that inherit from both `str` and `enum.Enum`.

## Why is this bad?

Python 3.11 introduced `enum.StrEnum`, which is preferred over inheriting
from both `str` and `enum.Enum`.

## Example

```python
import enum

class Foo(str, enum.Enum): ...
```

Use instead:

```python
import enum

class Foo(enum.StrEnum): ...
```

## Fix safety

Python 3.11 introduced a [breaking change](https://blog.pecar.me/python-enum) for enums that inherit from both
`str` and `enum.Enum`. Consider the following enum:

```python
from enum import Enum

class Foo(str, Enum):
    BAR = "bar"
```

In Python 3.11, the formatted representation of `Foo.BAR` changed as
follows:

```python
# Python 3.10
f"{Foo.BAR}"  # > bar
# Python 3.11
f"{Foo.BAR}"  # > Foo.BAR
```

Migrating from `str` and `enum.Enum` to `enum.StrEnum` will restore the
previous behavior, such that:

```python
from enum import StrEnum

class Foo(StrEnum):
    BAR = "bar"

f"{Foo.BAR}"  # > bar
```

As such, migrating to `enum.StrEnum` will introduce a behavior change for
code that relies on the Python 3.11 behavior.

## Options

- [`target-version`](../../settings/#target-version)

## References

- [enum.StrEnum](https://docs.python.org/3/library/enum.html#enum.StrEnum)
