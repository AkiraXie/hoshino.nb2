# map-int-version-parsing (RUF048)

Added in [0.10.0](https://github.com/astral-sh/ruff/releases/tag/0.10.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27map-int-version-parsing%27%20OR%20RUF048)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fruff%2Frules%2Fmap_int_version_parsing.rs#L37)

## What it does

Checks for calls of the form `map(int, __version__.split("."))`.

## Why is this bad?

`__version__` does not always contain integral-like elements.

```python
import matplotlib  # `__version__ == "3.9.1.post-1"` in our environment

# ValueError: invalid literal for int() with base 10: 'post1'
tuple(map(int, matplotlib.__version__.split(".")))
```

See also [*Version specifiers* | Packaging spec](https://packaging.python.org/en/latest/specifications/version-specifiers/#version-specifiers).

## Example

```python
tuple(map(int, matplotlib.__version__.split(".")))
```

Use instead:

```python
import packaging.version as version

version.parse(matplotlib.__version__)
```
