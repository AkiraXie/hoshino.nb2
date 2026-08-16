# nonlocal-and-global (PLE0115)

Added in [0.5.0](https://github.com/astral-sh/ruff/releases/tag/0.5.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27nonlocal-and-global%27%20OR%20PLE0115)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpylint%2Frules%2Fnonlocal_and_global.rs#L43)

Derived from the **[Pylint](../#pylint-pl)** linter.

## What it does

Checks for variables which are both declared as both `nonlocal` and
`global`.

## Why is this bad?

A `nonlocal` variable is a variable that is defined in the nearest
enclosing scope, but not in the global scope, while a `global` variable is
a variable that is defined in the global scope.

Declaring a variable as both `nonlocal` and `global` is contradictory and
will raise a `SyntaxError`.

## Example

```python
counter = 0

def increment():
    global counter
    nonlocal counter
    counter += 1
```

Use instead:

```python
counter = 0

def increment():
    global counter
    counter += 1
```

## References

- [Python documentation: The `global` statement](https://docs.python.org/3/reference/simple_stmts.html#the-global-statement)
- [Python documentation: The `nonlocal` statement](https://docs.python.org/3/reference/simple_stmts.html#nonlocal)
