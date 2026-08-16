# write-whole-file (FURB103)

Preview (since [v0.3.6](https://github.com/astral-sh/ruff/releases/tag/v0.3.6)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27write-whole-file%27%20OR%20FURB103)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Frefurb%2Frules%2Fwrite_whole_file.rs#L43)

Derived from the **[refurb](../#refurb-furb)** linter.

Fix is sometimes available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for uses of `open` and `write` that can be replaced by `pathlib`
methods, like `Path.write_text` and `Path.write_bytes`.

## Why is this bad?

When writing a single string to a file, it's simpler and more concise
to use `pathlib` methods like `Path.write_text` and `Path.write_bytes`
instead of `open` and `write` calls via `with` statements.

## Example

```python
with open("file.txt", "w") as f:
    f.write("some text")
```

Use instead:

```python
from pathlib import Path

Path("file.txt").write_text("some text")
```

## Fix Safety

This rule's fix is marked as unsafe if the replacement would remove comments attached to the original expression.

## References

- [Python documentation: `Path.write_bytes`](https://docs.python.org/3/library/pathlib.html#pathlib.Path.write_bytes)
- [Python documentation: `Path.write_text`](https://docs.python.org/3/library/pathlib.html#pathlib.Path.write_text)
