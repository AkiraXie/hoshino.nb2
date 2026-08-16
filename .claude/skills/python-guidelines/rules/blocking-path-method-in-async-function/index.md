# blocking-path-method-in-async-function (ASYNC240)

Added in [0.15.0](https://github.com/astral-sh/ruff/releases/tag/0.15.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27blocking-path-method-in-async-function%27%20OR%20ASYNC240)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fflake8_async%2Frules%2Fblocking_path_methods.rs#L49)

Derived from the **[flake8-async](../#flake8-async-async)** linter.

## What it does

Checks that async functions do not call blocking `os.path` or `pathlib.Path`
methods.

## Why is this bad?

Calling some `os.path` or `pathlib.Path` methods in an async function will block
the entire event loop, preventing it from executing other tasks while waiting
for the operation. This negates the benefits of asynchronous programming.

Instead, use the methods' async equivalents from `trio.Path` or `anyio.Path`.

## Example

```python
import os

async def func():
    path = "my_file.txt"
    file_exists = os.path.exists(path)
```

Use instead:

```python
import trio

async def func():
    path = trio.Path("my_file.txt")
    file_exists = await path.exists()
```

Non-blocking methods are OK to use:

```python
import pathlib

async def func():
    path = pathlib.Path("my_file.txt")
    file_dirname = path.dirname()
    new_path = os.path.join("/tmp/src/", path)
```
