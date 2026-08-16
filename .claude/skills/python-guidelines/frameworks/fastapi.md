# Fastapi Rules (Python)

3 rules that apply when the project uses **fastapi**.
Load this file only if the project's manifest imports or depends on
`fastapi`.

---

### fast-api-non-annotated-dependency (FAST002)
Avoid FastAPI routes with deprecated uses of `Depends` or similar.
❌ 
```
from fastapi import Depends, FastAPI
app = FastAPI()
async def common_parameters(q: str | None = None, skip: int = 0, limit: int = 100):
    return {"q": q, "skip": skip, "limit": limit}
@app.get("/items/")
async def read_items(commons: dict = Depends(common_parameters)):
…
```
✅ 
```
from typing import Annotated
from fastapi import Depends, FastAPI
app = FastAPI()
async def common_parameters(q: str | None = None, skip: int = 0, limit: int = 100):
    return {"q": q, "skip": skip, "limit": limit}
@app.get("/items/")
…
```

### fast-api-redundant-response-model (FAST001)
Avoid FastAPI routes that use the optional `response_model` parameter with the same type as the return type.
❌ 
```
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI()
class Item(BaseModel):
    name: str
@app.post("/items/", response_model=Item)
…
```
✅ 
```
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI()
class Item(BaseModel):
    name: str
@app.post("/items/")
…
```

### fast-api-unused-path-parameter (FAST003)
Avoid FastAPI routes that declare path parameters in the route path that are not included in the function signature.
❌ 
```
from fastapi import FastAPI
app = FastAPI()
@app.get("/things/{thing_id}")
async def read_thing(query: str): ...
```
✅ 
```
from fastapi import FastAPI
app = FastAPI()
@app.get("/things/{thing_id}")
async def read_thing(thing_id: int, query: str): ...
```
