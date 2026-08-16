# duplicate-bases (PLE0241)

Added in [v0.0.269](https://github.com/astral-sh/ruff/releases/tag/v0.0.269) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27duplicate-bases%27%20OR%20PLE0241)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fduplicate_bases.rs#L57)

Derived from the **[Pylint](../#pylint-pl)** linter.

Fix is sometimes available.

## What it does

Checks for duplicate base classes in class definitions.

## Why is this bad?

Including duplicate base classes will raise a `TypeError` at runtime.

## Example

```python
class Foo:
    pass

class Bar(Foo, Foo):
    pass
```

Use instead:

```python
class Foo:
    pass

class Bar(Foo):
    pass
```

## Fix safety

This rule's fix is marked as unsafe if there's comments in the
base classes, as comments may be removed.

For example, the fix would be marked as unsafe in the following case:

```python
class Foo:
    pass

class Bar(
    Foo,  # comment
    Foo,
):
    pass
```

## References

- [Python documentation: Class definitions](https://docs.python.org/3/reference/compound_stmts.html#class-definitions)
