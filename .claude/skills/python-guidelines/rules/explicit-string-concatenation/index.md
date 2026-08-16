# explicit-string-concatenation (ISC003)

Added in [v0.0.201](https://github.com/astral-sh/ruff/releases/tag/v0.0.201) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27explicit-string-concatenation%27%20OR%20ISC003)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_implicit_str_concat%2Frules%2Fexplicit.rs#L42)

Derived from the **[flake8-implicit-str-concat](../#flake8-implicit-str-concat-isc)** linter.

Fix is sometimes available.

## What it does

Checks for string literals that are explicitly concatenated (using the
`+` operator).

## Why is this bad?

For string literals that wrap across multiple lines, implicit string
concatenation within parentheses is preferred over explicit
concatenation using the `+` operator, as the former is more readable.

## Example

```python
z = (
    "The quick brown fox jumps over the lazy "
    + "dog"
)
```

Use instead:

```python
z = (
    "The quick brown fox jumps over the lazy "
    "dog"
)
```

## Options

Setting `lint.flake8-implicit-str-concat.allow-multiline = false` will disable this rule because
it would leave no allowed way to write a multi-line string.

- [`lint.flake8-implicit-str-concat.allow-multiline`](../../settings/#lint_flake8-implicit-str-concat_allow-multiline)
