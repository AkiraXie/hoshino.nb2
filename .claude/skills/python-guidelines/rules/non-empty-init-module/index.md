# non-empty-init-module (RUF067)

Preview (since [0.14.11](https://github.com/astral-sh/ruff/releases/tag/0.14.11)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27non-empty-init-module%27%20OR%20RUF067)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Fnon_empty_init_module.rs#L75)

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Detects the presence of code in `__init__.py` files.

## Why is this bad?

`__init__.py` files are often empty or only contain simple code to modify a module's API. As
such, it's easy to overlook them and their possible side effects when debugging.

## Example

Instead of defining `MyClass` directly in `__init__.py`:

```python
"""My module docstring."""

class MyClass:
    def my_method(self): ...
```

move the definition to another file, import it, and include it in `__all__`:

```python
"""My module docstring."""

from submodule import MyClass

__all__ = ["MyClass"]
```

Code in `__init__.py` files is also run at import time and can cause surprising slowdowns. To
disallow any code in `__init__.py` files, you can enable the
[`lint.ruff.strictly-empty-init-modules`](../../settings/#lint_ruff_strictly-empty-init-modules) setting. In this case:

```python
from submodule import MyClass

__all__ = ["MyClass"]
```

the only fix is entirely emptying the file:

```python

```

## Details

In non-strict mode, this rule allows several common patterns in `__init__.py` files:

- Imports
- Assignments to dunder names (identifiers starting and ending with `__`, such as `__all__` or
  `__submodules__`)
- Module-level and attribute docstrings
- `if TYPE_CHECKING` blocks
- [PEP-562](https://peps.python.org/pep-0562/) module-level `__getattr__` and `__dir__` functions

## Options

- [`lint.ruff.strictly-empty-init-modules`](../../settings/#lint_ruff_strictly-empty-init-modules)

## References

- [`flake8-empty-init-modules`](https://github.com/samueljsb/flake8-empty-init-modules/)
