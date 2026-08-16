# blocking-input-in-async-function (ASYNC250)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27blocking-input-in-async-function%27%20OR%20ASYNC250)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_async%2Frules%2Fblocking_input.rs#L35)

Derived from the **[flake8-async](../#flake8-async-async)** linter.

## What it does

Checks that async functions do not contain blocking usage of input from user.

## Why is this bad?

Blocking an async function via a blocking input call will block the entire
event loop, preventing it from executing other tasks while waiting for user
input, negating the benefits of asynchronous programming.

Instead of making a blocking input call directly, wrap the input call in
an executor to execute the blocking call on another thread.

## Example

```python
async def foo():
    username = input("Username:")
```

Use instead:

```python
import asyncio

async def foo():
    loop = asyncio.get_running_loop()
    username = await loop.run_in_executor(None, input, "Username:")
```
