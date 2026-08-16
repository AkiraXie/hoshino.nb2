# unused-noqa (RUF100)

Added in [v0.0.155](https://github.com/astral-sh/ruff/releases/tag/v0.0.155) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27unused-noqa%27%20OR%20RUF100)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Funused_noqa.rs#L83)

Fix is always available.

## What it does

Checks for `noqa` directives that are no longer applicable.

## Why is this bad?

A `noqa` directive that no longer matches any diagnostic violations is
likely included by mistake, and should be removed to avoid confusion.

## Example

```python
import foo  # noqa: F401

def bar():
    foo.bar()
```

Use instead:

```python
import foo

def bar():
    foo.bar()
```

## Conflict with other linters

When using `RUF100` with the `--fix` option, Ruff may remove trailing comments
that follow a `# noqa` directive on the same line, as it interprets the
remainder of the line as a description for the suppression.

To prevent Ruff from removing suppressions for other tools (like `pylint`
or `mypy`), separate them with a second `#` character:

```python
# Bad: Ruff --fix will remove the pylint comment
def visit_ImportFrom(self, node):  # noqa: N802, pylint: disable=invalid-name
    pass

# Good: Ruff will preserve the pylint comment
def visit_ImportFrom(self, node):  # noqa: N802 # pylint: disable=invalid-name
    pass
```

## See also

This rule ignores any codes that are unknown to Ruff, as it can't determine
if the codes are valid or used by other tools. Enable [`invalid-rule-code`](https://docs.astral.sh/ruff/rules/invalid-rule-code/)
to flag any unknown rule codes.

## References

- [Ruff error suppression](https://docs.astral.sh/ruff/linter/#error-suppression)
