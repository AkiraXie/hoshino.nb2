# fast-api-redundant-response-model (FAST001)

Added in [0.8.0](https://github.com/astral-sh/ruff/releases/tag/0.8.0) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27fast-api-redundant-response-model%27%20OR%20FAST001)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Ffastapi%2Frules%2Ffastapi_redundant_response_model.rs#L66)

Derived from the **[FastAPI](../#fastapi-fast)** linter.

Fix is always available.

## What it does

Checks for FastAPI routes that use the optional `response_model` parameter
with the same type as the return type.

## Why is this bad?

FastAPI routes automatically infer the response model type from the return
type, so specifying it explicitly is redundant.

The `response_model` parameter is used to override the default response
model type. For example, `response_model` can be used to specify that
a non-serializable response type should instead be serialized via an
alternative type.

For more information, see the [FastAPI documentation](https://fastapi.tiangolo.com/tutorial/response-model/).

## Example

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str

@app.post("/items/", response_model=Item)
async def create_item(item: Item) -> Item:
    return item
```

Use instead:

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str

@app.post("/items/")
async def create_item(item: Item) -> Item:
    return item
```

## Fix safety

This fix is always unsafe, as removing the `response_model` argument can change
runtime behavior and API documentation generation. Additionally, comments inside
the decorator might be removed when the argument is deleted.
