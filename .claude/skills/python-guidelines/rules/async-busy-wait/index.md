# async-busy-wait (ASYNC110)

Added in [0.5.0](https://github.com/astral-sh/ruff/releases/tag/0.5.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27async-busy-wait%27%20OR%20ASYNC110)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_async%2Frules%2Fasync_busy_wait.rs#L49)

Derived from the **[flake8-async](../#flake8-async-async)** linter.

## What it does

Checks for the use of an async sleep function in a `while` loop.

## Why is this bad?

Busy-waiting for a condition in a loop forces a tradeoff between
efficiency and latency: shorter sleep times improve responsiveness
but waste more CPU cycles, while longer sleep times reduce CPU usage
but delay reaction to state changes.

Waiting on an `Event` object like `asyncio.Event`, `trio.Event`, or
`anyio.Event` eliminates this tradeoff, allowing immediate response
with minimal wasted CPU time.

## Example

```python
import asyncio

DONE = False

async def func():
    while not DONE:
        await asyncio.sleep(1)
```

Use instead:

```python
import asyncio

DONE = asyncio.Event()

async def func():
    await DONE.wait()
```

## References

- [`asyncio` events](https://docs.python.org/3/library/asyncio-sync.html#asyncio.Event)
- [`anyio` events](https://anyio.readthedocs.io/en/latest/api.html#anyio.Event)
- [`trio` events](https://trio.readthedocs.io/en/latest/reference-core.html#trio.Event)
