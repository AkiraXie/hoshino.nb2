# f-string-number-format (FURB116)

Added in [0.13.0](https://github.com/astral-sh/ruff/releases/tag/0.13.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27f-string-number-format%27%20OR%20FURB116)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Frefurb%2Frules%2Ffstring_number_format.rs#L34)

Derived from the **[refurb](../#refurb-furb)** linter.

Fix is sometimes available.

## What it does

Checks for uses of `bin(...)[2:]` (or `hex`, or `oct`) to convert
an integer into a string.

## Why is this bad?

When converting an integer to a baseless binary, hexadecimal, or octal
string, using f-strings is more concise and readable than using the
`bin`, `hex`, or `oct` functions followed by a slice.

## Example

```python
print(bin(1337)[2:])
```

Use instead:

```python
print(f"{1337:b}")
```

## Fix safety

The fix is only marked as safe for integer literals, all other cases
are display-only, as they may change the runtime behavior of the program
or introduce syntax errors. The fix for integer literals is also marked as unsafe
if the expression contains comments that would be removed by the fix.
