# dataclass-enum (RUF049)

Added in [0.12.0](https://github.com/astral-sh/ruff/releases/tag/0.12.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27dataclass-enum%27%20OR%20RUF049)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Fdataclass_enum.rs#L47)

## What it does

Checks for enum classes which are also decorated with `@dataclass`.

## Why is this bad?

Decorating an enum with `@dataclass()` does not cause any errors at runtime,
but may cause erroneous results:

```python
@dataclass
class E(Enum):
    A = 1
    B = 2

print(E.A == E.B)  # True
```

## Example

```python
from dataclasses import dataclass
from enum import Enum

@dataclass
class E(Enum): ...
```

Use instead:

```python
from enum import Enum

class E(Enum): ...
```

## References

- [Python documentation: Enum HOWTO § Dataclass support](https://docs.python.org/3/howto/enum.html#dataclass-support)
