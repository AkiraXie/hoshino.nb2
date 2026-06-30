# hoshino.nb2 代码质量改进计划

## 指导原则

1. **表达式 > 语句** — 列表/字典/生成器表达式优先于 for-append 循环
2. **上下文管理器管状态** — 资源获取/释放成对出现，用 `with`/`async with`
3. **不问类型，直接调** — 鸭子类型，通过 platform 层统一访问，不 `isinstance`

**Simple is better than complex。不引入无谓的类和抽象层。**

## 执行清单

### A. 异常处理精度

**范围**：`hoshino/util/aiohttpx.py`

```python
# 改前
except BaseException as e:
    logger.error(...)
    raise

# 改后
except Exception as e:
    logger.error(...)
    raise
```

`BaseException` 会捕获 `KeyboardInterrupt`、`SystemExit`、`asyncio.CancelledError`，这些不应被当作 HTTP 请求错误处理。

### B. 导入时副作用

**范围**：`hoshino/modules/information/weibo/db.py`、`bilireq/utils.py`、`pushlive/db.py`、`interactive/alisten/util.py`、`interactive/qbitorrent/utils.py`

```python
# 改前 — import 时执行 DDL
Base.metadata.create_all(engine)

# 改后 — 启动钩子
from hoshino.hooks import on_startup

@on_startup
async def _ensure_schema():
    Base.metadata.create_all(engine)
    _ensure_schema_migrations()
```

涉及文件共 5 处 `create_all` + 3 处 `_ensure_schema()` 调用。统一改为惰性初始化或启动钩子。

### C. 类型标注统一

**范围**：全项目

```python
# 改前
from typing import Optional, Union
def foo(x: Optional[str]) -> Union[str, int]: ...

# 改后
def foo(x: str | None) -> str | int: ...
```

机械替换，`ruff` 有规则 `UP007` 可自动修复：`uv run ruff check --fix --select UP007 .`

### D. 表达式化

**范围**：`hoshino/util/__init__.py`、`hoshino/base/image.py`、各模块 handler

```python
# 改前
imgs = []
for s in msg:
    if s.type == "image":
        imgs.append(s)
return imgs

# 改后
return [s for s in msg if s.type == "image"]
```

扫一遍 `for-append` 模式，能用推导式替换的替换。保持可读性优先 — 嵌套超过两层或带复杂条件的保留 for 循环。

### E. 上下文管理器补全

**范围**：全项目

检查所有手动 `acquire()/release()`、`open()/close()` 是否可用 `with` 替代。已有的 DB session 管理 (`with Session()`) 已经是对的，确认无遗漏。

## 执行顺序

```
A (except BaseException)  →  1 文件，5 分钟
B (import 副作用)          →  5 文件，30 分钟
C (类型标注)               →  全项目 ruff --fix，5 分钟
D (表达式化)               →  渐进式，不阻塞
E (上下文管理器)           →  审计，不阻塞
```

A+B+C 一次性提交。D+E 渐进式改进。

## 验证

每批改进后：
- `uv run ruff check .` — 无新增 error
- 启动烟测 — 插件加载完成，正常 shutdown
