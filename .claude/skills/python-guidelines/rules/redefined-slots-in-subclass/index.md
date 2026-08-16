# redefined-slots-in-subclass (PLW0244)

Preview (since [0.9.3](https://github.com/astral-sh/ruff/releases/tag/0.9.3)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27redefined-slots-in-subclass%27%20OR%20PLW0244)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fredefined_slots_in_subclass.rs#L40)

Derived from the **[Pylint](../#pylint-pl)** linter.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for a re-defined slot in a subclass.

## Why is this bad?

If a class defines a slot also defined in a base class, the
instance variable defined by the base class slot is inaccessible
(except by retrieving its descriptor directly from the base class).

## Example

```python
class Base:
    __slots__ = ("a", "b")

class Subclass(Base):
    __slots__ = ("a", "d")  # slot "a" redefined
```

Use instead:

```python
class Base:
    __slots__ = ("a", "b")

class Subclass(Base):
    __slots__ = "d"
```
