# blank-lines-after-function-or-class (E305)

Preview (since [v0.2.2](https://github.com/astral-sh/ruff/releases/tag/v0.2.2)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27blank-lines-after-function-or-class%27%20OR%20E305)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpycodestyle%2Frules%2Fblank_lines.rs#L285)

Derived from the **[pycodestyle](../#pycodestyle-e-w)** linter.

Fix is always available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for missing blank lines after the end of function or class.

## Why is this bad?

PEP 8 recommends using blank lines as follows:

- Two blank lines are expected between functions and classes
- One blank line is expected between methods of a class.

## Example

```python
class User(object):
    pass
user = User()
```

Use instead:

```python
class User(object):
    pass

user = User()
```

## Typing stub files (`.pyi`)

The typing style guide recommends to not use blank lines between statements except to group
them. That's why this rule is not enabled in typing stub files.

## References

- [PEP 8: Blank Lines](https://peps.python.org/pep-0008/#blank-lines)
- [Flake 8 rule](https://www.flake8rules.com/rules/E305.html)
- [Typing Style Guide](https://typing.python.org/en/latest/guides/writing_stubs.html#blank-lines)
