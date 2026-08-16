# async-zero-sleep (ASYNC115)

Added in [0.5.0](https://github.com/astral-sh/ruff/releases/tag/0.5.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27async-zero-sleep%27%20OR%20ASYNC115)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_async%2Frules%2Fasync_zero_sleep.rs#L51)

Derived from the **[flake8-async](../#flake8-async-async)** linter.

Fix is always available.

## What it does

Checks for uses of `trio.sleep(0)` or `anyio.sleep(0)`.

## Why is this bad?

`trio.sleep(0)` is equivalent to calling `trio.lowlevel.checkpoint()`.
However, the latter better conveys the intent of the code.

## Example

```python
import trio

async def func():
    await trio.sleep(0)
```

Use instead:

```python
import trio.lowlevel

async def func():
    await trio.lowlevel.checkpoint()
```

## Fix safety

This rule's fix is marked as unsafe if there's comments in the
`trio.sleep(0)` expression, as comments may be removed.

For example, the fix would be marked as unsafe in the following case:

```python
import trio

async def func():
    await trio.sleep(  # comment
        # comment
        0
    )
```
