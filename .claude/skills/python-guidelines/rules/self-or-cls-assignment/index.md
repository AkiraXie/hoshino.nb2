# self-or-cls-assignment (PLW0642)

Added in [0.6.0](https://github.com/astral-sh/ruff/releases/tag/0.6.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27self-or-cls-assignment%27%20OR%20PLW0642)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fself_or_cls_assignment.rs#L53)

Derived from the **[Pylint](../#pylint-pl)** linter.

## What it does

Checks for assignment of `self` and `cls` in instance and class methods respectively.

This check also applies to `__new__` even though this is technically
a static method.

## Why is this bad?

The identifiers `self` and `cls` are conventional in Python for the first parameter of instance
methods and class methods, respectively. Assigning new values to these variables can be
confusing for others reading your code; using a different variable name can lead to clearer
code.

## Example

```python
class Version:
    def add(self, other):
        self = self + other
        return self

    @classmethod
    def superclass(cls):
        cls = cls.__mro__[-1]
        return cls
```

Use instead:

```python
class Version:
    def add(self, other):
        new_version = self + other
        return new_version

    @classmethod
    def superclass(cls):
        supercls = cls.__mro__[-1]
        return supercls
```

## Options

- [`lint.pep8-naming.classmethod-decorators`](../../settings/#lint_pep8-naming_classmethod-decorators)
- [`lint.pep8-naming.staticmethod-decorators`](../../settings/#lint_pep8-naming_staticmethod-decorators)
