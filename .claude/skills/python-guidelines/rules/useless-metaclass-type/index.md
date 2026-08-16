# useless-metaclass-type (UP001)

Added in [v0.0.155](https://github.com/astral-sh/ruff/releases/tag/v0.0.155) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27useless-metaclass-type%27%20OR%20UP001)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyupgrade%2Frules%2Fuseless_metaclass_type.rs#L31)

Derived from the **[pyupgrade](../#pyupgrade-up)** linter.

Fix is always available.

## What it does

Checks for the use of `__metaclass__ = type` in class definitions.

## Why is this bad?

Since Python 3, `__metaclass__ = type` is implied and can thus be omitted.

## Example

```python
class Foo:
    __metaclass__ = type
```

Use instead:

```python
class Foo: ...
```

## References

- [PEP 3115 – Metaclasses in Python 3000](https://peps.python.org/pep-3115/)
