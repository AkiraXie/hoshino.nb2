# Python Guidelines

Every rule below is a hard constraint. Apply when writing or modifying
Python code — not only during review. Rules are grouped by tier:

- **Tier 1 (correctness + security)**: violating these produces bugs or
  vulnerabilities. Never violate.
- **Tier 2 (modernization + performance)**: non-violation keeps code
  current and efficient. Match unless the project's toolchain forbids it.

For framework-specific rules (React, Django, etc.), load the matching
file from `frameworks/`. For Tier 3 style/pedantic rules, load `style.md`.
Full per-rule docs with edge cases: `rules/<slug>/index.md`.

---

## Tier 1 — Correctness & Security
*454 rules*

### Plugin: `Pyflakes`

### assert-tuple (F631)
Avoid `assert` statements that use non-empty tuples as test conditions.
❌ `assert (some_condition,)`
✅ `assert some_condition`

### break-outside-loop (F701)
Avoid `break` statements outside of loops.
❌ 
```
def foo():
    break
```

### continue-outside-loop (F702)
Avoid `continue` statements outside of loops.
❌ 
```
def foo():
    continue  # SyntaxError
```

### default-except-not-last (F707)
Avoid `except` blocks that handle all exceptions, but are not the last `except` block in a `try` statement.
❌ 
```
def reciprocal(n):
    try:
        reciprocal = 1 / n
    except:
        print("An exception occurred.")
    except ZeroDivisionError:
…
```
✅ 
```
def reciprocal(n):
    try:
        reciprocal = 1 / n
    except ZeroDivisionError:
        print("Cannot divide by zero.")
    except:
…
```

### expressions-in-star-assignment (F621)
Avoid the use of too many expressions in starred assignment statements.

### f-string-missing-placeholders (F541)
Avoid f-strings that do not contain any placeholder expressions.
❌ `f"Hello, world!"`
✅ `"Hello, world!"`

### forward-annotation-syntax-error (F722)
Avoid forward annotations that include invalid syntax.
❌ `def foo() -> "/": ...`

### future-feature-not-defined (F407)
Avoid `__future__` imports that are not defined in the current Python version.

### if-tuple (F634)
Avoid `if` statements that use non-empty tuples as test conditions.
❌ 
```
if (False,):
    print("This will always run")
```
✅ 
```
if False:
    print("This will never run")
```

### import-shadowed-by-loop-var (F402)
Avoid import bindings that are shadowed by loop variables.
❌ 
```
from os import path
for path in files:
    print(path)
```
✅ 
```
from os import path
for filename in files:
    print(filename)
```

### invalid-print-syntax (F633)
Avoid `print` statements that use the `>>` syntax.
❌ 
```
from __future__ import print_function
import sys
print >> sys.stderr, "Hello, world!"
```
✅ `print("Hello, world!", file=sys.stderr)`

### is-literal (F632)
Avoid `is` and `is not` comparisons against literals, like integers, strings, or lists.
❌ 
```
x = 200
if x is 200:
    print("It's 200!")
```
✅ 
```
x = 200
if x == 200:
    print("It's 200!")
```

### late-future-import (F404)
Avoid `__future__` imports that are not located at the beginning of a file.
❌ 
```
from pathlib import Path
from __future__ import annotations
```
✅ 
```
from __future__ import annotations
from pathlib import Path
```

### multi-value-repeated-key-literal (F601)
Avoid dictionary literals that associate multiple values with the same key.
❌ 
```
foo = {
    "bar": 1,
    "baz": 2,
    "baz": 3,
}
foo["baz"]  # 3
```
✅ 
```
foo = {
    "bar": 1,
    "baz": 2,
}
foo["baz"]  # 2
```

### multi-value-repeated-key-variable (F602)
Avoid dictionary keys that are repeated with different values.
❌ 
```
foo = {
    bar: 1,
    baz: 2,
    baz: 3,
}
foo[baz]  # 3
```
✅ 
```
foo = {
    bar: 1,
    baz: 2,
}
foo[baz]  # 2
```

### multiple-starred-expressions (F622)
Avoid the use of multiple starred expressions in assignment statements.
❌ `*foo, *bar, baz = (1, 2, 3)`

### percent-format-expected-mapping (F502)
Avoid named placeholders in `printf`-style format strings without mapping-type values.
❌ `"%(greeting)s, %(name)s" % ("Hello", "World")`
✅ `"%(greeting)s, %(name)s" % {"greeting": "Hello", "name": "World"}`

### percent-format-expected-sequence (F503)
Avoid uses of mapping-type values in `printf`-style format strings without named placeholders.
❌ `"%s, %s" % {"greeting": "Hello", "name": "World"}`
✅ `"%(greeting)s, %(name)s" % {"greeting": "Hello", "name": "World"}`

### percent-format-extra-named-arguments (F504)
Avoid unused mapping keys in `printf`-style format strings.
❌ `"Hello, %(name)s" % {"greeting": "Hello", "name": "World"}`
✅ `"Hello, %(name)s" % {"name": "World"}`

### percent-format-invalid-format (F501)
Avoid invalid `printf`-style format strings.
❌ `"Hello, %" % "world"`
✅ `"Hello, %s" % "world"`

### percent-format-missing-argument (F505)
Avoid named placeholders in `printf`-style format strings that are not present in the provided mapping.
❌ `"%(greeting)s, %(name)s" % {"name": "world"}`
✅ `"Hello, %(name)s" % {"name": "world"}`

### percent-format-mixed-positional-and-named (F506)
Avoid `printf`-style format strings that have mixed positional and named placeholders.
❌ `"%s, %(name)s" % ("Hello", {"name": "World"})`
✅ `"%s, %s" % ("Hello", "World")`

### percent-format-positional-count-mismatch (F507)
Avoid `printf`-style format strings that have a mismatch between the number of positional placeholders and the number of substitution values.
❌ `"%s, %s" % ("Hello", "world", "!")`
✅ `"%s, %s" % ("Hello", "world")`

### percent-format-star-requires-sequence (F508)
Avoid `printf`-style format strings that use the `*` specifier with non-tuple values.
❌ 
```
from math import pi
"%(n).*f" % {"n": (2, pi)}
```
✅ 
```
from math import pi
"%.*f" % (2, pi)  # 3.14
```

### percent-format-unsupported-format-character (F509)
Avoid `printf`-style format strings with invalid format characters.
❌ `"Hello, %S" % "world"`
✅ `"Hello, %s" % "world"`

### raise-not-implemented (F901)
Avoid `raise` statements that raise `NotImplemented`.
❌ 
```
class Foo:
    def bar(self):
        raise NotImplemented
```
✅ 
```
class Foo:
    def bar(self):
        raise NotImplementedError
```

### redefined-while-unused (F811)
Avoid variable definitions that redefine (or "shadow") unused variables.
❌ 
```
import foo
import bar
import foo  # Redefinition of unused `foo` from line 1
```
✅ 
```
import foo
import bar
```

### return-outside-function (F706)
Avoid `return` statements outside of functions.
❌ 
```
class Foo:
    return 1
```

### string-dot-format-extra-named-arguments (F522)
Avoid `str.format` calls with unused keyword arguments.
❌ `"Hello, {name}".format(greeting="Hello", name="World")`
✅ `"Hello, {name}".format(name="World")`

### string-dot-format-extra-positional-arguments (F523)
Avoid `str.format` calls with unused positional arguments.
❌ `"Hello, {0}".format("world", "!")`
✅ `"Hello, {0}".format("world")`

### string-dot-format-invalid-format (F521)
Avoid `str.format` calls with invalid format strings.
❌ `"{".format(foo)`
✅ `"{}".format(foo)`

### string-dot-format-missing-arguments (F524)
Avoid `str.format` calls with placeholders that are missing arguments.
❌ `"{greeting}, {name}".format(name="World")`
✅ `"{greeting}, {name}".format(greeting="Hello", name="World")`

### string-dot-format-mixing-automatic (F525)
Avoid `str.format` calls that mix automatic and manual numbering.
❌ `"{0}, {}".format("Hello", "World")`
✅ `"{0}, {1}".format("Hello", "World")`

### undefined-export (F822)
Avoid undefined names in `__all__`.
❌ 
```
from foo import bar
__all__ = ["bar", "baz"]  # undefined name `baz` in `__all__`
```
✅ 
```
from foo import bar, baz
__all__ = ["bar", "baz"]
```

### undefined-local (F823)
Avoid undefined local variables.
❌ 
```
x = 1
def foo():
    x += 1
```
✅ 
```
x = 1
def foo():
    global x
    x += 1
```

### undefined-local-with-import-star (F403)
Avoid the use of wildcard imports.
❌ 
```
from math import *
def area(radius):
    return pi * radius**2
```
✅ 
```
from math import pi
def area(radius):
    return pi * radius**2
```

### undefined-local-with-import-star-usage (F405)
Avoid names that might be undefined, but may also be defined in a wildcard import.
❌ 
```
from math import *
def area(radius):
    return pi * radius**2
```
✅ 
```
from math import pi
def area(radius):
    return pi * radius**2
```

### undefined-local-with-nested-import-star-usage (F406)
Avoid the use of wildcard imports outside of the module namespace.
❌ 
```
def foo():
    from math import *
```
✅ 
```
from math import *
def foo(): ...
```

### undefined-name (F821)
Avoid uses of undefined names.
❌ 
```
def double():
    return n * 2  # raises `NameError` if `n` is undefined when `double` is called
```
✅ 
```
def double(n):
    return n * 2
```

### unused-annotation (F842)
Avoid local variables that are annotated but never used.
❌ 
```
def foo():
    bar: int
```

### unused-import (F401)
Avoid unused imports.
❌ 
```
import numpy as np  # unused import
def area(radius):
    return 3.14 * radius**2
```
✅ 
```
def area(radius):
    return 3.14 * radius**2
```

### unused-variable (F841)
Avoid the presence of unused variables in function scopes.
❌ 
```
def foo():
    x = 1
    y = 2
    return x
```
✅ 
```
def foo():
    x = 1
    return x
```

### yield-outside-function (F704)
Avoid `yield`, `yield from`, and `await` usages outside of functions.
❌ 
```
class Foo:
    yield 1
```

### Plugin: `Pylint`

### await-outside-async (PLE1142)
Avoid uses of `await` outside `async` functions.
❌ 
```
import asyncio
def foo():
    await asyncio.sleep(1)
```
✅ 
```
import asyncio
async def foo():
    await asyncio.sleep(1)
```

### bad-str-strip-call (PLE1310)
Duplicate characters in `str.strip` calls.

### bad-string-format-character (PLE1300)
Avoid unsupported format types in format strings.

### bad-string-format-type (PLE1307)
Avoid mismatched argument types in "old-style" format strings.
❌ `print("%d" % "1")`
✅ `print("%d" % 1)`

### bidirectional-unicode (PLE2502)
Avoid bidirectional formatting characters.
❌ `example = "x‏" * 100  #    "‏x" is assigned`

### continue-in-finally (PLE0116)
Avoid `continue` statements inside `finally`
❌ 
```
while True:
    try:
        pass
    finally:
        continue
```
✅ 
```
while True:
    try:
        pass
    except Exception:
        pass
    else:
…
```

### dict-iter-missing-items (PLE1141)
Avoid dictionary unpacking in a for loop without calling `.items()`.
❌ 
```
data = {"Paris": 2_165_423, "New York City": 8_804_190, "Tokyo": 13_988_129}
for city, population in data:
    print(f"{city} has population {population}.")
```
✅ 
```
data = {"Paris": 2_165_423, "New York City": 8_804_190, "Tokyo": 13_988_129}
for city, population in data.items():
    print(f"{city} has population {population}.")
```

### duplicate-bases (PLE0241)
Avoid duplicate base classes in class definitions.
❌ 
```
class Foo:
    pass
class Bar(Foo, Foo):
    pass
```
✅ 
```
class Foo:
    pass
class Bar(Foo):
    pass
```

### invalid-all-format (PLE0605)
Avoid invalid assignments to `__all__`.
❌ `__all__ = "Foo"`
✅ `__all__ = ("Foo",)`

### invalid-all-object (PLE0604)
Avoid the inclusion of invalid objects in `__all__`.
❌ `__all__ = [Foo, 1, None]`
✅ `__all__ = ["Foo", "Bar", "Baz"]`

### invalid-bool-return-type (PLE0304)
Avoid `__bool__` implementations that return a type other than `bool`.
❌ 
```
class Foo:
    def __bool__(self):
        return 2
```
✅ 
```
class Foo:
    def __bool__(self):
        return True
```

### invalid-bytes-return-type (PLE0308)
Avoid `__bytes__` implementations that return types other than `bytes`.
❌ 
```
class Foo:
    def __bytes__(self):
        return 2
```
✅ 
```
class Foo:
    def __bytes__(self):
        return b"2"
```

### invalid-character-backspace (PLE2510)
Avoid strings that contain the control character `BS`.
❌ `x = ""`
✅ `x = "\b"`

### invalid-character-esc (PLE2513)
Avoid strings that contain the raw control character `ESC`.
❌ `x = ""`
✅ `x = "\x1b"`

### invalid-character-nul (PLE2514)
Avoid strings that contain the raw control character `NUL` (0 byte).
❌ `x = ""`
✅ `x = "\0"`

### invalid-character-sub (PLE2512)
Avoid strings that contain the raw control character `SUB`.
❌ `x = ""`
✅ `x = "\x1a"`

### invalid-character-zero-width-space (PLE2515)
Avoid strings that contain the zero width space character.
❌ `x = "Dear Sir/Madam"`
✅ `x = "Dear Sir\u200b/\u200bMadam"  # zero width space`

### invalid-envvar-value (PLE1507)
Avoid `os.getenv` calls with an invalid `key` argument.
❌ 
```
import os
os.getenv(1)
```
✅ 
```
import os
os.getenv("1")
```

### invalid-hash-return-type (PLE0309)
Avoid `__hash__` implementations that return non-integer values.
❌ 
```
class Foo:
    def __hash__(self):
        return "2"
```
✅ 
```
class Foo:
    def __hash__(self):
        return 2
```

### invalid-index-return-type (PLE0305)
Avoid `__index__` implementations that return non-integer values.
❌ 
```
class Foo:
    def __index__(self):
        return "2"
```
✅ 
```
class Foo:
    def __index__(self):
        return 2
```

### invalid-length-return-type (PLE0303)
Avoid `__len__` implementations that return values that are not non-negative integers.
❌ 
```
class Foo:
    def __len__(self):
        return "2"
```
✅ 
```
class Foo:
    def __len__(self):
        return 2
```

### invalid-str-return-type (PLE0307)
Avoid `__str__` implementations that return a type other than `str`.
❌ 
```
class Foo:
    def __str__(self):
        return True
```
✅ 
```
class Foo:
    def __str__(self):
        return "Foo"
```

### load-before-global-declaration (PLE0118)
Avoid uses of names that are declared as `global` prior to the relevant `global` declaration.
❌ 
```
counter = 1
def increment():
    print(f"Adding 1 to {counter}")
    global counter
    counter += 1
```
✅ 
```
counter = 1
def increment():
    global counter
    print(f"Adding 1 to {counter}")
    counter += 1
```

### logging-too-few-args (PLE1206)
Avoid too few positional arguments for a `logging` format string.
❌ 
```
import logging
try:
    function()
except Exception as e:
    logging.error("%s error occurred: %s", e)
    raise
```
✅ 
```
import logging
try:
    function()
except Exception as e:
    logging.error("%s error occurred: %s", type(e), e)
    raise
```

### logging-too-many-args (PLE1205)
Avoid too many positional arguments for a `logging` format string.
❌ 
```
import logging
try:
    function()
except Exception as e:
    logging.error("Error occurred: %s", type(e), e)
    raise
```
✅ 
```
import logging
try:
    function()
except Exception as e:
    logging.error("%s error occurred: %s", type(e), e)
    raise
```

### misplaced-bare-raise (PLE0704)
Avoid bare `raise` statements outside of exception handlers.
❌ 
```
from typing import Any
def is_some(obj: Any) -> bool:
    if obj is None:
        raise
```
✅ 
```
from typing import Any
def is_some(obj: Any) -> bool:
    if obj is None:
        raise ValueError("`obj` cannot be `None`")
```

### modified-iterating-set (PLE4703)
Avoid loops in which a `set` is modified during iteration.
❌ 
```
nums = {1, 2, 3}
for num in nums:
    nums.add(num + 5)
```
✅ 
```
nums = {1, 2, 3}
for num in nums.copy():
    nums.add(num + 5)
```

### non-slot-assignment (PLE0237)
Avoid assignments to attributes that are not defined in `__slots__`.
❌ 
```
class Student:
    __slots__ = ("name",)
    def __init__(self, name, surname):
        self.name = name
        self.surname = surname  # [assigning-non-slot]
        self.setup()
…
```
✅ 
```
class Student:
    __slots__ = ("name", "surname")
    def __init__(self, name, surname):
        self.name = name
        self.surname = surname
        self.setup()
…
```

### nonlocal-and-global (PLE0115)
Avoid variables which are both declared as both `nonlocal` and `global`.
❌ 
```
counter = 0
def increment():
    global counter
    nonlocal counter
    counter += 1
```
✅ 
```
counter = 0
def increment():
    global counter
    counter += 1
```

### nonlocal-without-binding (PLE0117)
Avoid `nonlocal` names without bindings.
❌ 
```
def foo():
    def get_bar(self):
        nonlocal bar
        ...
```
✅ 
```
def foo():
    bar = 1
    def get_bar(self):
        nonlocal bar
        ...
```

### potential-index-error (PLE0643)
Avoid hard-coded sequence accesses that are known to be out of bounds.
❌ `print([0, 1, 2][3])`

### repeated-keyword-argument (PLE1132)
Avoid repeated keyword arguments in function calls.
❌ `func(1, 2, c=3, **{"c": 4})`

### return-in-init (PLE0101)
Avoid `__init__` methods that return values.
❌ 
```
class Example:
    def __init__(self):
        return []
```
✅ 
```
class Example:
    def __init__(self):
        self.value = []
```

### singledispatch-method (PLE1519)
Avoid methods decorated with `@singledispatch`.
❌ 
```
from functools import singledispatch
class Class:
    @singledispatch
    def method(self, arg): ...
```
✅ 
```
from functools import singledispatchmethod
class Class:
    @singledispatchmethod
    def method(self, arg): ...
```

### singledispatchmethod-function (PLE1520)
Avoid non-method functions decorated with `@singledispatchmethod`.
❌ 
```
from functools import singledispatchmethod
@singledispatchmethod
def func(arg): ...
```
✅ 
```
from functools import singledispatch
@singledispatch
def func(arg): ...
```

### unexpected-special-method-signature (PLE0302)
Avoid "special" methods that have an unexpected method signature.
❌ 
```
class Bookshelf:
    def __init__(self):
        self._books = ["Foo", "Bar", "Baz"]
    def __len__(self, index):  # __len__ does not except an index parameter
        return len(self._books)
    def __getitem__(self, index):
…
```
✅ 
```
class Bookshelf:
    def __init__(self):
        self._books = ["Foo", "Bar", "Baz"]
    def __len__(self):
        return len(self._books)
    def __getitem__(self, index):
…
```

### yield-from-in-async-function (PLE1700)
Avoid uses of `yield from` in async functions.
❌ 
```
async def numbers():
    yield from [1, 2, 3, 4, 5]
```
✅ 
```
async def numbers():
    async for number in [1, 2, 3, 4, 5]:
        yield number
```

### yield-in-init (PLE0100)
Avoid `__init__` methods that are turned into generators by the inclusion of `yield` or `yield from` expressions.
❌ 
```
class InitIsGenerator:
    def __init__(self, i):
        yield i
```

### Plugin: `flake8-async`

### async-busy-wait (ASYNC110)
Avoid the use of an async sleep function in a `while` loop.
❌ 
```
import asyncio
DONE = False
async def func():
    while not DONE:
        await asyncio.sleep(1)
```
✅ 
```
import asyncio
DONE = asyncio.Event()
async def func():
    await DONE.wait()
```

### async-function-with-timeout (ASYNC109)
Avoid `async` function definitions with `timeout` parameters.
❌ 
```
async def long_running_task(timeout): ...
async def main():
    await long_running_task(timeout=2)
```
✅ 
```
async def long_running_task(): ...
async def main():
    async with asyncio.timeout(2):
        await long_running_task()
```

### async-zero-sleep (ASYNC115)
Avoid uses of `trio.sleep(0)` or `anyio.sleep(0)`.
❌ 
```
import trio
async def func():
    await trio.sleep(0)
```
✅ 
```
import trio.lowlevel
async def func():
    await trio.lowlevel.checkpoint()
```

### blocking-http-call-httpx-in-async-function (ASYNC212)
Ensure async functions do not use blocking httpx clients.
❌ 
```
import httpx
async def fetch():
    client = httpx.Client()
    response = client.get(...)
```
✅ 
```
import httpx
async def fetch():
    async with httpx.AsyncClient() as client:
        response = await client.get(...)
```

### blocking-http-call-in-async-function (ASYNC210)
Ensure async functions do not contain blocking HTTP calls.
❌ 
```
import urllib
async def fetch():
    urllib.request.urlopen("https://example.com/foo/bar").read()
```
✅ 
```
import aiohttp
async def fetch():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://example.com/foo/bar") as resp:
            ...
```

### blocking-input-in-async-function (ASYNC250)
Ensure async functions do not contain blocking usage of input from user.
❌ 
```
async def foo():
    username = input("Username:")
```
✅ 
```
import asyncio
async def foo():
    loop = asyncio.get_running_loop()
    username = await loop.run_in_executor(None, input, "Username:")
```

### blocking-open-call-in-async-function (ASYNC230)
Ensure async functions do not open files with blocking methods like `open`.
❌ 
```
async def foo():
    with open("bar.txt") as f:
        contents = f.read()
```
✅ 
```
import anyio
async def foo():
    async with await anyio.open_file("bar.txt") as f:
        contents = await f.read()
```

### blocking-path-method-in-async-function (ASYNC240)
Ensure async functions do not call blocking `os.path` or `pathlib.Path` methods.
❌ 
```
import os
async def func():
    path = "my_file.txt"
    file_exists = os.path.exists(path)
```
✅ 
```
import trio
async def func():
    path = trio.Path("my_file.txt")
    file_exists = await path.exists()
```

### blocking-sleep-in-async-function (ASYNC251)
Ensure async functions do not call `time.sleep`.
❌ 
```
import time
async def fetch():
    time.sleep(1)
```
✅ 
```
import asyncio
async def fetch():
    await asyncio.sleep(1)
```

### cancel-scope-no-checkpoint (ASYNC100)
Avoid timeout context managers which do not contain a checkpoint.
❌ 
```
import asyncio
async def func():
    async with asyncio.timeout(2):
        do_something()
```
✅ 
```
import asyncio
async def func():
    async with asyncio.timeout(2):
        do_something()
        await awaitable()
```

### create-subprocess-in-async-function (ASYNC220)
Ensure async functions do not create subprocesses with blocking methods.
❌ 
```
import os
async def foo():
    os.popen(cmd)
```
✅ 
```
import asyncio
async def foo():
    asyncio.create_subprocess_shell(cmd)
```

### long-sleep-not-forever (ASYNC116)
Avoid uses of `trio.sleep()` or `anyio.sleep()` with a delay greater than 24 hours.
❌ 
```
import trio
async def func():
    await trio.sleep(86401)
```
✅ 
```
import trio
async def func():
    await trio.sleep_forever()
```

### run-process-in-async-function (ASYNC221)
Ensure async functions do not run processes with blocking methods.
❌ 
```
import subprocess
async def foo():
    subprocess.run(cmd)
```
✅ 
```
import asyncio
async def foo():
    asyncio.create_subprocess_shell(cmd)
```

### trio-sync-call (ASYNC105)
Avoid calls to trio functions that are not immediately awaited.
❌ 
```
import trio
async def double_sleep(x):
    trio.sleep(2 * x)
```
✅ 
```
import trio
async def double_sleep(x):
    await trio.sleep(2 * x)
```

### wait-for-process-in-async-function (ASYNC222)
Ensure async functions do not wait on processes with blocking methods.
❌ 
```
import os
async def foo():
    os.waitpid(0)
```
✅ 
```
import asyncio
import os
def wait_for_process():
    os.waitpid(0)
async def foo():
    await asyncio.loop.run_in_executor(None, wait_for_process)
```

### Plugin: `flake8-bandit`

### assert (S101)
Avoid uses of the `assert` keyword.
❌ `assert x > 0, "Expected positive value."`

### bad-file-permissions (S103)
Avoid files with overly permissive permissions.
❌ 
```
import os
os.chmod("/etc/secrets.txt", 0o666)  # rw-rw-rw-
```
✅ 
```
import os
os.chmod("/etc/secrets.txt", 0o600)  # rw-------
```

### call-with-shell-equals-true (S604)
Avoid method calls that set the `shell` parameter to `true` or another truthy value when invoking a subprocess.
❌ 
```
import my_custom_subprocess
user_input = input("Enter a command: ")
my_custom_subprocess.run(user_input, shell=True)
```

### django-extra (S610)
Avoid uses of Django's `extra` function where one or more arguments passed are not literal expressions.

### django-raw-sql (S611)
Avoid uses of Django's `RawSQL` function.
❌ 
```
from django.db.models.expressions import RawSQL
from django.contrib.auth.models import User
User.objects.annotate(val=RawSQL("%s" % input_param, []))
```

### exec-builtin (S102)
Avoid uses of the builtin `exec` function.
❌ `exec("print('Hello World')")`

### flask-debug-true (S201)
Avoid uses of `debug=True` in Flask.
❌ 
```
from flask import Flask
app = Flask()
app.run(debug=True)
```
✅ 
```
import os
from flask import Flask
app = Flask()
app.run(debug=os.environ["ENV"] == "dev")
```

### hardcoded-bind-all-interfaces (S104)
Avoid hardcoded bindings to all network interfaces (`0.0.0.0`).
❌ `ALLOWED_HOSTS = ["0.0.0.0"]`
✅ `ALLOWED_HOSTS = ["127.0.0.1", "localhost"]`

### hardcoded-password-default (S107)
Avoid potential uses of hardcoded passwords in function argument defaults.
❌ `def connect_to_server(password="hunter2"): ...`
✅ 
```
import os
def connect_to_server(password=os.environ["PASSWORD"]): ...
```

### hardcoded-password-func-arg (S106)
Avoid potential uses of hardcoded passwords in function calls.
❌ `connect_to_server(password="hunter2")`
✅ 
```
import os
connect_to_server(password=os.environ["PASSWORD"])
```

### hardcoded-password-string (S105)
Avoid potential uses of hardcoded passwords in strings.
❌ `SECRET_KEY = "hunter2"`
✅ 
```
import os
SECRET_KEY = os.environ["SECRET_KEY"]
```

### hardcoded-sql-expression (S608)
Avoid strings that resemble SQL statements involved in some form string building operation.
❌ `query = "DELETE FROM foo WHERE id = '%s'" % identifier`

### hardcoded-temp-file (S108)
Avoid the use of hardcoded temporary file or directory paths.
❌ 
```
with open("/tmp/foo.txt", "w") as file:
    ...
```
✅ 
```
import tempfile
with tempfile.NamedTemporaryFile() as file:
    ...
```

### hashlib-insecure-hash-function (S324)
Avoid uses of weak or broken cryptographic hash functions in `hashlib` and `crypt` libraries.
❌ 
```
import hashlib
def certificate_is_valid(certificate: bytes, known_hash: str) -> bool:
    hash = hashlib.md5(certificate).hexdigest()
    return hash == known_hash
```
✅ 
```
import hashlib
def certificate_is_valid(certificate: bytes, known_hash: str) -> bool:
    hash = hashlib.sha256(certificate).hexdigest()
    return hash == known_hash
```

### jinja2-autoescape-false (S701)
Avoid `jinja2` templates that use `autoescape=False`.
❌ 
```
import jinja2
jinja2.Environment(loader=jinja2.FileSystemLoader("."))
```
✅ 
```
import jinja2
jinja2.Environment(loader=jinja2.FileSystemLoader("."), autoescape=True)
```

### logging-config-insecure-listen (S612)
Avoid insecure `logging.config.listen` calls.
❌ 
```
import logging
logging.config.listen(9999)
```

### mako-templates (S702)
Avoid uses of the `mako` templates.
❌ 
```
from mako.template import Template
Template("hello")
```
✅ 
```
from mako.template import Template
Template("hello |h")
```

### paramiko-call (S601)
Avoid `paramiko` calls.
❌ 
```
import paramiko
client = paramiko.SSHClient()
client.exec_command("echo $HOME")
```

### request-with-no-cert-validation (S501)
Avoid HTTPS requests that disable SSL certificate checks.
❌ 
```
import requests
requests.get("https://www.example.com", verify=False)
```
✅ 
```
import requests
requests.get("https://www.example.com")  # By default, `verify=True`.
```

### request-without-timeout (S113)
Avoid uses of the Python `requests` or `httpx` module that omit the `timeout` parameter.
❌ 
```
import requests
requests.get("https://www.example.com/")
```
✅ 
```
import requests
requests.get("https://www.example.com/", timeout=10)
```

### snmp-insecure-version (S508)
Avoid uses of SNMPv1 or SNMPv2.
❌ 
```
from pysnmp.hlapi import CommunityData
CommunityData("public", mpModel=0)
```
✅ 
```
from pysnmp.hlapi import CommunityData
CommunityData("public", mpModel=2)
```

### snmp-weak-cryptography (S509)
Avoid uses of the SNMPv3 protocol without encryption.
❌ 
```
from pysnmp.hlapi import UsmUserData
UsmUserData("user")
```
✅ 
```
from pysnmp.hlapi import UsmUserData
UsmUserData("user", "authkey", "privkey")
```

### ssh-no-host-key-verification (S507)
Avoid uses of policies disabling SSH verification in Paramiko.
❌ 
```
from paramiko import client
ssh_client = client.SSHClient()
ssh_client.set_missing_host_key_policy(client.AutoAddPolicy)
```
✅ 
```
from paramiko import client
ssh_client = client.SSHClient()
ssh_client.set_missing_host_key_policy(client.RejectPolicy)
```

### ssl-insecure-version (S502)
Avoid function calls with parameters that indicate the use of insecure SSL and TLS protocol versions.
❌ 
```
import ssl
ssl.wrap_socket(ssl_version=ssl.PROTOCOL_TLSv1)
```
✅ 
```
import ssl
ssl.wrap_socket(ssl_version=ssl.PROTOCOL_TLSv1_2)
```

### ssl-with-bad-defaults (S503)
Avoid function definitions with default arguments set to insecure SSL and TLS protocol versions.
❌ 
```
import ssl
def func(version=ssl.PROTOCOL_TLSv1): ...
```
✅ 
```
import ssl
def func(version=ssl.PROTOCOL_TLSv1_2): ...
```

### ssl-with-no-version (S504)
Avoid calls to `ssl.wrap_socket()` without an `ssl_version`.
❌ 
```
import ssl
ssl.wrap_socket()
```
✅ 
```
import ssl
ssl.wrap_socket(ssl_version=ssl.PROTOCOL_TLSv1_2)
```

### start-process-with-a-shell (S605)
Avoid calls that start a process with a shell, providing guidance on whether the usage is safe or not.

### start-process-with-no-shell (S606)
Avoid functions that start a process without a shell.
❌ 
```
import os
def insecure_function(arbitrary_user_input: str):
    os.spawnlp(os.P_NOWAIT, "/bin/mycmd", "mycmd", arbitrary_user_input)
```

### start-process-with-partial-path (S607)
Avoid the starting of a process with a partial executable path.
❌ 
```
import subprocess
subprocess.Popen(["ruff", "check", "file.py"])
```
✅ 
```
import subprocess
subprocess.Popen(["/usr/bin/ruff", "check", "file.py"])
```

### subprocess-popen-with-shell-equals-true (S602)
Avoid method calls that initiate a subprocess with a shell.
❌ 
```
import subprocess
subprocess.run("ls -l", shell=True)
```
✅ 
```
import subprocess
subprocess.run(["ls", "-l"])
```

### subprocess-without-shell-equals-true (S603)
Avoid method calls that initiate a subprocess without a shell.
❌ 
```
import subprocess
cmd = input("Enter a command: ").split()
subprocess.run(cmd)
```

### suspicious-eval-usage (S307)
Avoid uses of the builtin `eval()` function.
❌ `x = eval(input("Enter a number: "))`
✅ 
```
from ast import literal_eval
x = literal_eval(input("Enter a number: "))
```

### suspicious-ftp-lib-usage (S321)
Avoid the use of FTP-related functions.

### suspicious-ftplib-import (S402)
Avoid imports of the `ftplib` module.
❌ `import ftplib`

### suspicious-httpoxy-import (S412)
Avoid imports of `wsgiref.handlers.CGIHandler` and `twisted.web.twcgi.CGIScript`.
❌ `from wsgiref.handlers import CGIHandler`

### suspicious-insecure-cipher-mode-usage (S305)
Avoid uses of weak or broken cryptographic cipher modes.
❌ 
```
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
algorithm = algorithms.ARC4(key)
cipher = Cipher(algorithm, mode=modes.ECB(iv))
encryptor = cipher.encryptor()
```
✅ 
```
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
algorithm = algorithms.ARC4(key)
cipher = Cipher(algorithm, mode=modes.CTR(iv))
encryptor = cipher.encryptor()
```

### suspicious-insecure-cipher-usage (S304)
Avoid uses of weak or broken cryptographic ciphers.
❌ 
```
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
algorithm = algorithms.ARC4(key)
cipher = Cipher(algorithm, mode=None)
encryptor = cipher.encryptor()
```
✅ 
```
from cryptography.fernet import Fernet
fernet = Fernet(key)
```

### suspicious-insecure-hash-usage (S303)
Avoid uses of weak or broken cryptographic hash functions.
❌ 
```
from cryptography.hazmat.primitives import hashes
digest = hashes.Hash(hashes.MD5())
digest.update(b"Hello, world!")
digest.finalize()
```
✅ 
```
from cryptography.hazmat.primitives import hashes
digest = hashes.Hash(hashes.SHA256())
digest.update(b"Hello, world!")
digest.finalize()
```

### suspicious-lxml-import (S410)
Avoid imports of the `lxml` module.
❌ `import lxml`

### suspicious-mark-safe-usage (S308)
Avoid uses of calls to `django.utils.safestring.mark_safe`.
❌ 
```
from django.utils.safestring import mark_safe
def render_username(username):
    return mark_safe(f"<i>{username}</i>")  # Dangerous if username is user-provided.
```
✅ 
```
from django.utils.html import format_html
def render_username(username):
    return format_html("<i>{}</i>", username)  # username is escaped.
```

### suspicious-marshal-usage (S302)
Avoid calls to `marshal` functions.
❌ 
```
import marshal
with open("foo.marshal", "rb") as file:
    foo = marshal.load(file)
```
✅ 
```
import json
with open("foo.json", "rb") as file:
    foo = json.load(file)
```

### suspicious-mktemp-usage (S306)
Avoid uses of `tempfile.mktemp`.
❌ 
```
import tempfile
tmp_file = tempfile.mktemp()
with open(tmp_file, "w") as file:
    file.write("Hello, world!")
```
✅ 
```
import tempfile
with tempfile.TemporaryFile() as file:
    file.write("Hello, world!")
```

### suspicious-non-cryptographic-random-usage (S311)
Avoid uses of cryptographically weak pseudo-random number generators.
❌ 
```
import random
random.randrange(10)
```
✅ 
```
import secrets
secrets.randbelow(10)
```

### suspicious-pickle-import (S403)
Avoid imports of the `pickle`, `cPickle`, `dill`, and `shelve` modules.
❌ `import pickle`

### suspicious-pickle-usage (S301)
Avoid calls to `pickle` functions or modules that wrap them.
❌ 
```
import pickle
with open("foo.pickle", "rb") as file:
    foo = pickle.load(file)
```
✅ 
```
import json
with open("foo.json", "rb") as file:
    foo = json.load(file)
```

### suspicious-pycrypto-import (S413)
Avoid imports of several unsafe cryptography modules.
❌ `import Crypto.Random`

### suspicious-pyghmi-import (S415)
Avoid imports of the `pyghmi` module.
❌ `import pyghmi`

### suspicious-subprocess-import (S404)
Avoid imports of the `subprocess` module.
❌ `import subprocess`

### suspicious-telnet-usage (S312)
Avoid the use of Telnet-related functions.

### suspicious-telnetlib-import (S401)
Avoid imports of the `telnetlib` module.
❌ `import telnetlib`

### suspicious-unverified-context-usage (S323)
Avoid uses of `ssl._create_unverified_context`.
❌ 
```
import ssl
context = ssl._create_unverified_context()
```
✅ 
```
import ssl
context = ssl.create_default_context()
```

### suspicious-url-open-usage (S310)
Avoid instances where URL open functions are used with unexpected schemes.
❌ 
```
from urllib.request import urlopen
url = input("Enter a URL: ")
with urlopen(url) as response:
    ...
```
✅ 
```
from urllib.request import urlopen
url = input("Enter a URL: ")
if not url.startswith(("http:", "https:")):
    raise ValueError("URL must start with 'http:' or 'https:'")
with urlopen(url) as response:
    ...
```

### suspicious-xml-element-tree-usage (S314)
Avoid uses of insecure XML parsers.
❌ 
```
from xml.etree.ElementTree import parse
tree = parse("untrusted.xml")  # Vulnerable to XML attacks.
```
✅ 
```
from defusedxml.ElementTree import parse
tree = parse("untrusted.xml")
```

### suspicious-xml-etree-import (S405)
Avoid imports of the `xml.etree.cElementTree` and `xml.etree.ElementTree` modules
❌ `import xml.etree.cElementTree`

### suspicious-xml-expat-builder-usage (S316)
Avoid uses of insecure XML parsers.
❌ 
```
from xml.dom.expatbuilder import parse
parse("untrusted.xml")
```
✅ 
```
from defusedxml.expatbuilder import parse
tree = parse("untrusted.xml")
```

### suspicious-xml-expat-import (S407)
Avoid imports of the `xml.dom.expatbuilder` module.
❌ `import xml.dom.expatbuilder`

### suspicious-xml-expat-reader-usage (S315)
Avoid uses of insecure XML parsers.
❌ 
```
from xml.sax.expatreader import create_parser
parser = create_parser()
```
✅ 
```
from defusedxml.sax import create_parser
parser = create_parser()
```

### suspicious-xml-mini-dom-usage (S318)
Avoid uses of insecure XML parsers.
❌ 
```
from xml.dom.minidom import parse
content = parse("untrusted.xml")
```
✅ 
```
from defusedxml.minidom import parse
content = parse("untrusted.xml")
```

### suspicious-xml-minidom-import (S408)
Avoid imports of the `xml.dom.minidom` module.
❌ `import xml.dom.minidom`

### suspicious-xml-pull-dom-usage (S319)
Avoid uses of insecure XML parsers.
❌ 
```
from xml.dom.pulldom import parse
content = parse("untrusted.xml")
```
✅ 
```
from defusedxml.pulldom import parse
content = parse("untrusted.xml")
```

### suspicious-xml-pulldom-import (S409)
Avoid imports of the `xml.dom.pulldom` module.
❌ `import xml.dom.pulldom`

### suspicious-xml-sax-import (S406)
Avoid imports of the `xml.sax` module.
❌ `import xml.sax`

### suspicious-xml-sax-usage (S317)
Avoid uses of insecure XML parsers.
❌ 
```
from xml.sax import make_parser
make_parser()
```
✅ 
```
from defusedxml.sax import make_parser
make_parser()
```

### suspicious-xmlc-element-tree-usage (S313)
Avoid uses of insecure XML parsers.
❌ 
```
from xml.etree.cElementTree import parse
tree = parse("untrusted.xml")  # Vulnerable to XML attacks.
```
✅ 
```
from defusedxml.cElementTree import parse
tree = parse("untrusted.xml")
```

### suspicious-xmle-tree-usage (S320)
Avoid uses of insecure XML parsers.
❌ 
```
from lxml import etree
content = etree.parse("untrusted.xml")
```

### suspicious-xmlrpc-import (S411)
Avoid imports of the `xmlrpc` module.
❌ `import xmlrpc`

### tarfile-unsafe-members (S202)
Avoid uses of `tarfile.extractall`.
❌ 
```
import tarfile
import tempfile
tar = tarfile.open(filename)
tar.extractall(path=tempfile.mkdtemp())
tar.close()
```

### try-except-continue (S112)
Avoid uses of the `try`-`except`-`continue` pattern.
❌ 
```
import logging
while predicate:
    try:
        ...
    except Exception:
        continue
```
✅ 
```
import logging
while predicate:
    try:
        ...
    except Exception as exc:
        logging.exception("Error occurred")
```

### try-except-pass (S110)
Avoid uses of the `try`-`except`-`pass` pattern.
❌ 
```
try:
    ...
except Exception:
    pass
```
✅ 
```
import logging
try:
    ...
except Exception as exc:
    logging.exception("Exception occurred")
```

### unix-command-wildcard-injection (S609)
Avoid possible wildcard injections in calls to `subprocess.Popen()`.
❌ 
```
import subprocess
subprocess.Popen(["chmod", "777", "*.py"], shell=True)
```
✅ 
```
import subprocess
subprocess.Popen(["chmod", "777", "main.py"], shell=True)
```

### unsafe-markup-use (S704)
Avoid non-literal strings being passed to `markupsafe.Markup`.
❌ 
```
from markupsafe import Markup
content = "<script>alert('Hello, world!')</script>"
html = Markup(f"<b>{content}</b>")  # XSS
```
✅ 
```
from markupsafe import Markup
content = "<script>alert('Hello, world!')</script>"
html = Markup("<b>{}</b>").format(content)  # Safe
```

### unsafe-yaml-load (S506)
Avoid uses of the `yaml.load` function.
❌ 
```
import yaml
yaml.load(untrusted_yaml)
```
✅ 
```
import yaml
yaml.safe_load(untrusted_yaml)
```

### weak-cryptographic-key (S505)
Avoid uses of cryptographic keys with vulnerable key sizes.
❌ 
```
from cryptography.hazmat.primitives.asymmetric import dsa, ec
dsa.generate_private_key(key_size=512)
ec.generate_private_key(curve=ec.SECT163K1())
```
✅ 
```
from cryptography.hazmat.primitives.asymmetric import dsa, ec
dsa.generate_private_key(key_size=4096)
ec.generate_private_key(curve=ec.SECP384R1())
```

### Plugin: `flake8-blind-except`

### blind-except (BLE001)
Avoid `except` clauses that catch all exceptions.
❌ 
```
try:
    foo()
except BaseException:
    ...
```
✅ 
```
try:
    foo()
except FileNotFoundError:
    ...
```

### Plugin: `flake8-bugbear`

### abstract-base-class-without-abstract-method (B024)
Avoid abstract classes without abstract methods or properties.
❌ 
```
from abc import ABC
from typing import ClassVar
class Foo(ABC):
    class_var: ClassVar[str] = "assigned"
    def method(self):
        bar()
```
✅ 
```
from abc import ABC, abstractmethod
from typing import ClassVar
class Foo(ABC):
    class_var: ClassVar[str]  # unassigned
    @abstractmethod
    def method(self):
…
```

### assert-false (B011)
Avoid uses of `assert False`.
❌ `assert False`
✅ `raise AssertionError`

### assert-raises-exception (B017)
Avoid `assertRaises` and `pytest.raises` context managers that catch `Exception` or `BaseException`.
❌ `self.assertRaises(Exception, foo)`
✅ `self.assertRaises(SomeSpecificException, foo)`

### assignment-to-os-environ (B003)
Avoid assignments to `os.environ`.
❌ 
```
import os
os.environ = {"foo": "bar"}
```
✅ 
```
import os
os.environ.clear()
os.environ["foo"] = "bar"
```

### batched-without-explicit-strict (B911)
Avoid `itertools.batched` calls without an explicit `strict` parameter.
❌ 
```
import itertools
itertools.batched(iterable, n)
```

### cached-instance-method (B019)
Avoid uses of the `functools.lru_cache` and `functools.cache` decorators on methods.
❌ 
```
from functools import lru_cache
def square(x: int) -> int:
    return x * x
class Number:
    value: int
    @lru_cache
…
```
✅ 
```
from functools import lru_cache
@lru_cache
def square(x: int) -> int:
    return x * x
class Number:
    value: int
…
```

### class-as-data-structure (B903)
Avoid classes that only have a public `__init__` method, without base classes and decorators.
❌ 
```
class Point:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
```
✅ 
```
from dataclasses import dataclass
@dataclass
class Point:
    x: float
    y: float
```

### del-attr-with-constant (B043)
Avoid uses of `delattr` that take a constant attribute value as an argument (e.g., `delattr(obj, "foo")`).
❌ `delattr(obj, "foo")`
✅ `del obj.foo`

### duplicate-handler-exception (B014)
Avoid exception handlers that catch duplicate exceptions.
❌ 
```
try:
    ...
except (Exception, ValueError):  # `Exception` includes `ValueError`.
    ...
```
✅ 
```
try:
    ...
except Exception:
    ...
```

### duplicate-try-block-exception (B025)
Avoid `try-except` blocks with duplicate exception handlers.
❌ 
```
try:
    ...
except ValueError:
    ...
except ValueError:
    ...
```
✅ 
```
try:
    ...
except ValueError:
    ...
```

### duplicate-value (B033)
Avoid set literals that contain duplicate items.
❌ `{1, 2, 3, 1}`
✅ `{1, 2, 3}`

### empty-method-without-abstract-decorator (B027)
Avoid empty methods in abstract base classes without an abstract decorator.
❌ 
```
from abc import ABC
class Foo(ABC):
    def method(self): ...
```
✅ 
```
from abc import ABC, abstractmethod
class Foo(ABC):
    @abstractmethod
    def method(self): ...
```

### except-with-empty-tuple (B029)
Avoid exception handlers that catch an empty tuple.
❌ 
```
try:
    1 / 0
except ():
    ...
```
✅ 
```
try:
    1 / 0
except ZeroDivisionError:
    ...
```

### except-with-non-exception-classes (B030)
Avoid exception handlers that catch non-exception classes.
❌ 
```
try:
    1 / 0
except 1:
    ...
```
✅ 
```
try:
    1 / 0
except ZeroDivisionError:
    ...
```

### f-string-docstring (B021)
Avoid docstrings that are written via f-strings.
❌ 
```
def foo():
    f"""Not a docstring."""
```
✅ 
```
def foo():
    """A docstring."""
```

### function-call-in-default-argument (B008)
Avoid function calls in default function arguments.
❌ 
```
def create_list() -> list[int]:
    return [1, 2, 3]
def mutable_default(arg: list[int] = create_list()) -> list[int]:
    arg.append(4)
    return arg
```
✅ 
```
def better(arg: list[int] | None = None) -> list[int]:
    if arg is None:
        arg = create_list()
    arg.append(4)
    return arg
```

### function-uses-loop-variable (B023)
Avoid function definitions that use a loop variable.
❌ 
```
adders = [lambda x: x + i for i in range(3)]
values = [adder(1) for adder in adders]  # [3, 3, 3]
```
✅ 
```
adders = [lambda x, i=i: x + i for i in range(3)]
values = [adder(1) for adder in adders]  # [1, 2, 3]
```

### get-attr-with-constant (B009)
Avoid uses of `getattr` that take a constant attribute value as an argument (e.g., `getattr(obj, "foo")`).
❌ `getattr(obj, "foo")`
✅ `obj.foo`

### jump-statement-in-finally (B012)
Avoid `break`, `continue`, and `return` statements in `finally` blocks.
❌ 
```
def speed(distance, time):
    try:
        return distance / time
    except ZeroDivisionError:
        raise ValueError("Time cannot be zero")
    finally:
…
```
✅ 
```
def speed(distance, time):
    try:
        return distance / time
    except ZeroDivisionError:
        raise ValueError("Time cannot be zero")
```

### loop-iterator-mutation (B909)
Avoid mutations to an iterable during a loop iteration.
❌ 
```
items = [1, 2, 3]
for item in items:
    print(item)
    # Create an infinite loop by appending to the list.
    items.append(item)
```

### loop-variable-overrides-iterator (B020)
Avoid loop control variables that override the loop iterable.
❌ 
```
items = [1, 2, 3]
for items in items:
    print(items)
```
✅ 
```
items = [1, 2, 3]
for item in items:
    print(item)
```

### map-without-explicit-strict (B912)
Avoid `map` calls without an explicit `strict` parameter when called with two or more iterables, or any starred argument.
❌ `map(f, a, b)`
✅ `map(f, a, b, strict=True)`

### mutable-argument-default (B006)
Avoid uses of mutable objects as function argument defaults.
❌ 
```
def add_to_list(item, some_list=[]):
    some_list.append(item)
    return some_list
l1 = add_to_list(0)  # [0]
l2 = add_to_list(1)  # [0, 1]
```
✅ 
```
def add_to_list(item, some_list=None):
    if some_list is None:
        some_list = []
    some_list.append(item)
    return some_list
l1 = add_to_list(0)  # [0]
…
```

### mutable-contextvar-default (B039)
Avoid uses of mutable objects as `ContextVar` defaults.
❌ 
```
from contextvars import ContextVar
cv: ContextVar[list] = ContextVar("cv", default=[])
```
✅ 
```
from contextvars import ContextVar
cv: ContextVar[list | None] = ContextVar("cv", default=None)
...
if cv.get() is None:
    cv.set([])
```

### no-explicit-stacklevel (B028)
Avoid `warnings.warn` calls without an explicit `stacklevel` keyword argument.
❌ 
```
import warnings
warnings.warn("This is a warning")
```
✅ 
```
import warnings
warnings.warn("This is a warning", stacklevel=2)
```

### raise-literal (B016)
Avoid `raise` statements that raise a literal value.
❌ `raise "foo"`
✅ `raise Exception("foo")`

### raise-without-from-inside-except (B904)
Avoid `raise` statements in exception handlers that lack a `from` clause.
❌ 
```
try:
    ...
except FileNotFoundError:
    if ...:
        raise RuntimeError("...")
    else:
…
```
✅ 
```
try:
    ...
except FileNotFoundError as exc:
    if ...:
        raise RuntimeError("...") from None
    else:
…
```

### re-sub-positional-args (B034)
Avoid calls to `re.sub`, `re.subn`, and `re.split` that pass `count`, `maxsplit`, or `flags` as positional arguments.
❌ 
```
import re
re.split("pattern", "replacement", 1)
```
✅ 
```
import re
re.split("pattern", "replacement", maxsplit=1)
```

### redundant-tuple-in-exception-handler (B013)
Avoid single-element tuples in exception handlers (e.g., `except (ValueError,):`).
❌ 
```
try:
    ...
except (ValueError,):
    ...
```
✅ 
```
try:
    ...
except ValueError:
    ...
```

### return-in-generator (B901)
Avoid `return {value}` statements in functions that also contain `yield` or `yield from` statements.
❌ 
```
from collections.abc import Iterable
from pathlib import Path
def get_file_paths(file_types: Iterable[str] | None = None) -> Iterable[Path]:
    dir_path = Path(".")
    if file_types is None:
        return dir_path.glob("*")
…
```
✅ 
```
from collections.abc import Iterable
from pathlib import Path
def get_file_paths(file_types: Iterable[str] | None = None) -> Iterable[Path]:
    dir_path = Path(".")
    if file_types is None:
        yield from dir_path.glob("*")
…
```

### reuse-of-groupby-generator (B031)
Avoid multiple usage of the generator returned from `itertools.groupby()`.

### set-attr-with-constant (B010)
Avoid uses of `setattr` that take a constant attribute value as an argument (e.g., `setattr(obj, "foo", 42)`).
❌ `setattr(obj, "foo", 42)`
✅ `obj.foo = 42`

### star-arg-unpacking-after-keyword-arg (B026)
Avoid function calls that use star-argument unpacking after providing a keyword argument

### static-key-dict-comprehension (B035)
Avoid dictionary comprehensions that use a static key, like a string literal or a variable defined outside the comprehension.
❌ 
```
data = ["some", "Data"]
{"key": value.upper() for value in data}
```
✅ 
```
data = ["some", "Data"]
{value: value.upper() for value in data}
```

### strip-with-multi-characters (B005)
Avoid uses of multi-character strings in `.strip()`, `.lstrip()`, and `.rstrip()` calls.
❌ `"text.txt".strip(".txt")  # "e"`
✅ `"text.txt".removesuffix(".txt")  # "text"`

### unary-prefix-increment-decrement (B002)
Avoid the attempted use of the unary prefix increment (`++`) or decrement operator (`--`).
❌ 
```
++x
--y
```
✅ 
```
x += 1
y -= 1
```

### unintentional-type-annotation (B032)
Avoid the unintentional use of type annotations.
❌ `a["b"]: 1`
✅ `a["b"] = 1`

### unreliable-callable-check (B004)
Avoid uses of `hasattr` to test if an object is callable (e.g., `hasattr(obj, "__call__")`).
❌ `hasattr(obj, "__call__")`
✅ `callable(obj)`

### unused-loop-control-variable (B007)
Avoid unused variables in loops (e.g., `for` and `while` statements).
❌ 
```
for i, j in foo:
    bar(i)
```
✅ 
```
for i, _j in foo:
    bar(i)
```

### useless-comparison (B015)
Avoid useless comparisons.
❌ `foo == bar`
✅ `assert foo == bar, "`foo` and `bar` should be equal."`

### useless-contextlib-suppress (B022)
Avoid `contextlib.suppress` without arguments.
❌ 
```
import contextlib
with contextlib.suppress():
    foo()
```
✅ 
```
import contextlib
with contextlib.suppress(Exception):
    foo()
```

### useless-expression (B018)
Avoid useless expressions.
❌ `1 + 1`
✅ `foo = 1 + 1`

### zip-without-explicit-strict (B905)
Avoid `zip` calls without an explicit `strict` parameter when called with two or more iterables, or any starred argument.
❌ `zip(a, b)`
✅ `zip(a, b, strict=True)`

### Plugin: `flake8-datetimez`

### call-date-fromtimestamp (DTZ012)
Avoid usage of `datetime.date.fromtimestamp()`.
❌ 
```
import datetime
datetime.date.fromtimestamp(946684800)
```
✅ 
```
import datetime
datetime.datetime.fromtimestamp(946684800, tz=datetime.timezone.utc).date()
```

### call-date-today (DTZ011)
Avoid usage of `datetime.date.today()`.
❌ 
```
import datetime
datetime.date.today()
```
✅ 
```
import datetime
datetime.datetime.now(tz=datetime.timezone.utc).date()
```

### call-datetime-fromtimestamp (DTZ006)
Avoid usage of `datetime.datetime.fromtimestamp()` that do not specify a timezone.
❌ 
```
import datetime
datetime.datetime.fromtimestamp(946684800)
```
✅ 
```
import datetime
datetime.datetime.fromtimestamp(946684800, tz=datetime.timezone.utc)
```

### call-datetime-now-without-tzinfo (DTZ005)
Avoid usages of `datetime.datetime.now()` that do not specify a timezone.
❌ 
```
import datetime
datetime.datetime.now()
```
✅ 
```
import datetime
datetime.datetime.now(tz=datetime.timezone.utc)
```

### call-datetime-strptime-without-zone (DTZ007)
Avoid uses of `datetime.datetime.strptime()` that lead to naive datetime objects.
❌ 
```
import datetime
datetime.datetime.strptime("2022/01/31", "%Y/%m/%d")
```

### call-datetime-today (DTZ002)
Avoid usage of `datetime.datetime.today()`.
❌ 
```
import datetime
datetime.datetime.today()
```
✅ 
```
import datetime
datetime.datetime.now(tz=datetime.timezone.utc)
```

### call-datetime-utcfromtimestamp (DTZ004)
Avoid usage of `datetime.datetime.utcfromtimestamp()`.
❌ 
```
import datetime
datetime.datetime.utcfromtimestamp(946684800)
```
✅ 
```
import datetime
datetime.datetime.fromtimestamp(946684800, tz=datetime.timezone.utc)
```

### call-datetime-utcnow (DTZ003)
Avoid usage of `datetime.datetime.utcnow()`.
❌ 
```
import datetime
datetime.datetime.utcnow()
```
✅ 
```
import datetime
datetime.datetime.now(tz=datetime.timezone.utc)
```

### call-datetime-without-tzinfo (DTZ001)
Avoid `datetime` instantiations that do not specify a timezone.
❌ 
```
import datetime
datetime.datetime(2000, 1, 1, 0, 0, 0)
```
✅ 
```
import datetime
datetime.datetime(2000, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
```

### datetime-min-max (DTZ901)
Avoid uses of `datetime.datetime.min` and `datetime.datetime.max`.
❌ 
```
import datetime
datetime.datetime.max
```
✅ 
```
import datetime
datetime.datetime.max.replace(tzinfo=datetime.UTC)
```

### Plugin: `flake8-errmsg`

### dot-format-in-exception (EM103)
Avoid the use of `.format` calls on string literals in exception constructors.
❌ 
```
sub = "Some value"
raise RuntimeError("'{}' is incorrect".format(sub))
```

### f-string-in-exception (EM102)
Avoid the use of f-strings in exception constructors.
❌ 
```
sub = "Some value"
raise RuntimeError(f"{sub!r} is incorrect")
```

### raw-string-in-exception (EM101)
Avoid the use of string literals in exception constructors.
❌ `raise RuntimeError("'Some value' is incorrect")`

### Plugin: `flake8-gettext`

### f-string-in-get-text-func-call (INT001)
Avoid f-strings in `gettext` function calls.
❌ 
```
from gettext import gettext as _
name = "Maria"
_(f"Hello, {name}!")  # Looks for "Hello, Maria!".
```
✅ 
```
from gettext import gettext as _
name = "Maria"
_("Hello, %s!") % name  # Looks for "Hello, %s!".
```

### format-in-get-text-func-call (INT002)
Avoid `str.format` calls in `gettext` function calls.
❌ 
```
from gettext import gettext as _
name = "Maria"
_("Hello, {}!".format(name))  # Looks for "Hello, Maria!".
```
✅ 
```
from gettext import gettext as _
name = "Maria"
_("Hello, %s!") % name  # Looks for "Hello, %s!".
```

### printf-in-get-text-func-call (INT003)
Avoid printf-style formatted strings in `gettext` function calls.
❌ 
```
from gettext import gettext as _
name = "Maria"
_("Hello, %s!" % name)  # Looks for "Hello, Maria!".
```
✅ 
```
from gettext import gettext as _
name = "Maria"
_("Hello, %s!") % name  # Looks for "Hello, %s!".
```

### Plugin: `flake8-import-conventions`

### banned-import-alias (ICN002)
Avoid imports that use non-standard naming conventions, like `import tensorflow.keras.backend as K`.
❌ `import tensorflow.keras.backend as K`
✅ 
```
import tensorflow as tf
tf.keras.backend
```

### banned-import-from (ICN003)
Avoid member imports that should instead be accessed by importing the module.
❌ `from pandas import Series`
✅ 
```
import pandas as pd
pd.Series
```

### unconventional-import-alias (ICN001)
Avoid imports that are typically imported using a common convention, like `import pandas as pd`, and enforces that convention.
❌ `import pandas`
✅ `import pandas as pd`

### Plugin: `flake8-logging`

### direct-logger-instantiation (LOG001)
Avoid direct instantiation of `logging.Logger`, as opposed to using `logging.getLogger()`.
❌ 
```
import logging
logger = logging.Logger(__name__)
```
✅ 
```
import logging
logger = logging.getLogger(__name__)
```

### exc-info-outside-except-handler (LOG014)
Avoid logging calls with `exc_info=` outside exception handlers.
❌ 
```
import logging
logging.warning("Foobar", exc_info=True)
```
✅ 
```
import logging
logging.warning("Foobar")
```

### exception-without-exc-info (LOG007)
Avoid uses of `logging.exception()` with `exc_info` set to `False`.
❌ `logging.exception("...", exc_info=False)`
✅ `logging.error("...")`

### invalid-get-logger-argument (LOG002)
Avoid any usage of `__cached__` and `__file__` as an argument to `logging.getLogger()`.
❌ 
```
import logging
logger = logging.getLogger(__file__)
```
✅ 
```
import logging
logger = logging.getLogger(__name__)
```

### log-exception-outside-except-handler (LOG004)
Avoid `.exception()` logging calls outside of exception handlers.
❌ 
```
import logging
logging.exception("Foobar")
```
✅ 
```
import logging
logging.error("Foobar")
```

### root-logger-call (LOG015)
Avoid usages of the following `logging` top-level functions: `debug`, `info`, `warn`, `warning`, `error`, `critical`, `log`, `exception`.
❌ 
```
import logging
logging.info("Foobar")
```
✅ 
```
import logging
logger = logging.getLogger(__name__)
logger.info("Foobar")
```

### undocumented-warn (LOG009)
Avoid uses of `logging.WARN`.
❌ 
```
import logging
logging.basicConfig(level=logging.WARN)
```
✅ 
```
import logging
logging.basicConfig(level=logging.WARNING)
```

### Plugin: `flake8-logging-format`

### logging-exc-info (G201)
Avoid uses of `logging.error` that pass `exc_info=True`.
❌ 
```
import logging
try:
    ...
except ValueError:
    logging.error("Exception occurred", exc_info=True)
```
✅ 
```
import logging
try:
    ...
except ValueError:
    logging.exception("Exception occurred")
```

### logging-extra-attr-clash (G101)
Avoid `extra` keywords in logging statements that clash with `LogRecord` attributes.
❌ 
```
import logging
logging.basicConfig(format="%(name) - %(message)s", level=logging.INFO)
username = "Maria"
logging.info("Something happened", extra=dict(name=username))
```
✅ 
```
import logging
logging.basicConfig(format="%(user_id)s - %(message)s", level=logging.INFO)
username = "Maria"
logging.info("Something happened", extra=dict(user_id=username))
```

### logging-f-string (G004)
Avoid uses of f-strings to format logging messages.
❌ 
```
import logging
logging.basicConfig(format="%(message)s", level=logging.INFO)
user = "Maria"
logging.info(f"{user} - Something happened")
```
✅ 
```
import logging
logging.basicConfig(format="%(user_id)s - %(message)s", level=logging.INFO)
user = "Maria"
logging.info("Something happened", extra=dict(user_id=user))
```

### logging-percent-format (G002)
Avoid uses of `printf`-style format strings to format logging messages.
❌ 
```
import logging
logging.basicConfig(format="%(message)s", level=logging.INFO)
user = "Maria"
logging.info("%s - Something happened" % user)
```
✅ 
```
import logging
logging.basicConfig(format="%(user_id)s - %(message)s", level=logging.INFO)
user = "Maria"
logging.info("Something happened", extra=dict(user_id=user))
```

### logging-redundant-exc-info (G202)
Avoid redundant `exc_info` keyword arguments in logging statements.
❌ 
```
import logging
try:
    ...
except ValueError:
    logging.exception("Exception occurred", exc_info=True)
```
✅ 
```
import logging
try:
    ...
except ValueError:
    logging.exception("Exception occurred")
```

### logging-string-concat (G003)
Avoid uses string concatenation via the `+` operator to format logging messages.
❌ 
```
import logging
logging.basicConfig(format="%(message)s", level=logging.INFO)
user = "Maria"
logging.info(user + " - Something happened")
```
✅ 
```
import logging
logging.basicConfig(format="%(user_id)s - %(message)s", level=logging.INFO)
user = "Maria"
logging.info("Something happened", extra=dict(user_id=user))
```

### logging-string-format (G001)
Avoid uses of `str.format` to format logging messages.
❌ 
```
import logging
logging.basicConfig(format="%(message)s", level=logging.INFO)
user = "Maria"
logging.info("{} - Something happened".format(user))
```
✅ 
```
import logging
logging.basicConfig(format="%(user_id)s - %(message)s", level=logging.INFO)
user = "Maria"
logging.info("Something happened", extra={"user_id": user})
```

### logging-warn (G010)
Avoid uses of `logging.warn` and `logging.Logger.warn`.
❌ 
```
import logging
logging.warn("Something happened")
```
✅ 
```
import logging
logging.warning("Something happened")
```

### Plugin: `flake8-pie`

### duplicate-class-field-definition (PIE794)
Avoid duplicate field definitions in classes.
❌ 
```
class Person:
    name = Tom
    ...
    name = Ben
```
✅ 
```
class Person:
    name = Tom
    ...
```

### multiple-starts-ends-with (PIE810)
Avoid `startswith` or `endswith` calls on the same value with different prefixes or suffixes.
❌ 
```
msg = "Hello, world!"
if msg.startswith("Hello") or msg.startswith("Hi"):
    print("Greetings!")
```
✅ 
```
msg = "Hello, world!"
if msg.startswith(("Hello", "Hi")):
    print("Greetings!")
```

### non-unique-enums (PIE796)
Avoid enums that contain duplicate values.
❌ 
```
from enum import Enum
class Foo(Enum):
    A = 1
    B = 2
    C = 1
```
✅ 
```
from enum import Enum
class Foo(Enum):
    A = 1
    B = 2
    C = 3
```

### reimplemented-container-builtin (PIE807)
Avoid lambdas that can be replaced with the `list` or `dict` builtins.
❌ 
```
from dataclasses import dataclass, field
@dataclass
class Foo:
    bar: list[int] = field(default_factory=lambda: [])
```
✅ 
```
from dataclasses import dataclass, field
@dataclass
class Foo:
    bar: list[int] = field(default_factory=list)
    baz: dict[str, int] = field(default_factory=dict)
```

### unnecessary-dict-kwargs (PIE804)
Avoid unnecessary `dict` kwargs.

### unnecessary-placeholder (PIE790)
Avoid unnecessary `pass` statements and ellipsis (`...`) literals in functions, classes, and other blocks.
❌ 
```
def func():
    """Placeholder docstring."""
    pass
```
✅ 
```
def func():
    """Placeholder docstring."""
```

### unnecessary-range-start (PIE808)
Avoid `range` calls with an unnecessary `start` argument.
❌ `range(0, 3)`
✅ `range(3)`

### unnecessary-spread (PIE800)
Avoid unnecessary dictionary unpacking operators (`**`).
❌ 
```
foo = {"A": 1, "B": 2}
bar = {**foo, **{"C": 3}}
```
✅ 
```
foo = {"A": 1, "B": 2}
bar = {**foo, "C": 3}
```

### Plugin: `flake8-pytest-style`

### pytest-assert-always-false (PT015)
Avoid `assert` statements whose test expression is a falsy value.
❌ 
```
def test_foo():
    if some_condition:
        assert False, "some_condition was True"
```
✅ 
```
import pytest
def test_foo():
    if some_condition:
        pytest.fail("some_condition was True")
    ...
```

### pytest-assert-in-except (PT017)
Avoid `assert` statements in `except` clauses.
❌ 
```
def test_foo():
    try:
        1 / 0
    except ZeroDivisionError as e:
        assert e.args
```
✅ 
```
import pytest
def test_foo():
    with pytest.raises(ZeroDivisionError) as exc_info:
        1 / 0
    assert exc_info.value.args
```

### pytest-composite-assertion (PT018)
Avoid assertions that combine multiple independent conditions.
❌ 
```
def test_foo():
    assert something and something_else
def test_bar():
    assert not (something or something_else)
```
✅ 
```
def test_foo():
    assert something
    assert something_else
def test_bar():
    assert not something
    assert not something_else
```

### pytest-deprecated-yield-fixture (PT020)
Avoid `pytest.yield_fixture` usage.
❌ 
```
import pytest
@pytest.yield_fixture()
def my_fixture():
    obj = SomeClass()
    yield obj
    obj.cleanup()
```
✅ 
```
import pytest
@pytest.fixture()
def my_fixture():
    obj = SomeClass()
    yield obj
    obj.cleanup()
```

### pytest-duplicate-parametrize-test-cases (PT014)
Avoid duplicate test cases in `pytest.mark.parametrize`.
❌ 
```
import pytest
@pytest.mark.parametrize(
    ("param1", "param2"),
    [
        (1, 2),
        (1, 2),
…
```
✅ 
```
import pytest
@pytest.mark.parametrize(
    ("param1", "param2"),
    [
        (1, 2),
    ],
…
```

### pytest-erroneous-use-fixtures-on-fixture (PT025)
Avoid `pytest.mark.usefixtures` decorators applied to `pytest` fixtures.
❌ 
```
import pytest
@pytest.fixture()
def a():
    pass
@pytest.mark.usefixtures("a")
@pytest.fixture()
…
```
✅ 
```
import pytest
@pytest.fixture()
def a():
    pass
@pytest.fixture()
def b(a):
…
```

### pytest-extraneous-scope-function (PT003)
Avoid `pytest.fixture` calls with `scope="function"`.
❌ 
```
import pytest
@pytest.fixture(scope="function")
def my_fixture(): ...
```
✅ 
```
import pytest
@pytest.fixture()
def my_fixture(): ...
```

### pytest-fail-without-message (PT016)
Avoid `pytest.fail` calls without a message.
❌ 
```
import pytest
def test_foo():
    pytest.fail()
def test_bar():
    pytest.fail("")
def test_baz():
…
```
✅ 
```
import pytest
def test_foo():
    pytest.fail("...")
def test_bar():
    pytest.fail(reason="...")
```

### pytest-fixture-finalizer-callback (PT021)
Avoid unnecessary `request.addfinalizer` usages in `pytest` fixtures.
❌ 
```
import pytest
@pytest.fixture()
def my_fixture(request):
    resource = acquire_resource()
    request.addfinalizer(resource.release)
    return resource
```

### pytest-fixture-incorrect-parentheses-style (PT001)
Avoid argument-free `@pytest.fixture()` decorators with or without parentheses, depending on the `lint.flake8-pytest-style.fixture-parentheses` setting.
❌ 
```
import pytest
@pytest.fixture()
def my_fixture(): ...
```
✅ 
```
import pytest
@pytest.fixture
def my_fixture(): ...
```

### pytest-fixture-param-without-value (PT019)
Avoid `pytest` test functions that should be decorated with `@pytest.mark.usefixtures`.
❌ 
```
import pytest
@pytest.fixture
def _patch_something(): ...
def test_foo(_patch_something): ...
```
✅ 
```
import pytest
@pytest.fixture
def _patch_something(): ...
@pytest.mark.usefixtures("_patch_something")
def test_foo(): ...
```

### pytest-fixture-positional-args (PT002)
Avoid `pytest.fixture` calls with positional arguments.
❌ 
```
import pytest
@pytest.fixture("module")
def my_fixture(): ...
```
✅ 
```
import pytest
@pytest.fixture(scope="module")
def my_fixture(): ...
```

### pytest-incorrect-fixture-name-underscore (PT005)
Avoid `pytest` fixtures that return a value, but are named with a leading underscore.
❌ 
```
import pytest
@pytest.fixture()
def _some_object():
    return SomeClass()
@pytest.fixture()
def _some_object_with_cleanup():
…
```
✅ 
```
import pytest
@pytest.fixture()
def some_object():
    return SomeClass()
@pytest.fixture()
def some_object_with_cleanup():
…
```

### pytest-incorrect-mark-parentheses-style (PT023)
Avoid argument-free `@pytest.mark.<marker>()` decorators with or without parentheses, depending on the `lint.flake8-pytest-style.mark-parentheses` setting.
❌ 
```
import pytest
@pytest.mark.foo()
def test_something(): ...
```
✅ 
```
import pytest
@pytest.mark.foo
def test_something(): ...
```

### pytest-incorrect-pytest-import (PT013)
Avoid incorrect import of pytest.
❌ 
```
import pytest as pt
from pytest import fixture
```
✅ `import pytest`

### pytest-missing-fixture-name-underscore (PT004)
Avoid `pytest` fixtures that do not return a value, but are not named with a leading underscore.
❌ 
```
import pytest
@pytest.fixture()
def patch_something(mocker):
    mocker.patch("module.object")
@pytest.fixture()
def use_context():
…
```
✅ 
```
import pytest
@pytest.fixture()
def _patch_something(mocker):
    mocker.patch("module.object")
@pytest.fixture()
def _use_context():
…
```

### pytest-parameter-with-default-argument (PT028)
Avoid parameters of test functions with default arguments.
❌ `def test_foo(a=1): ...`
✅ `def test_foo(a): ...`

### pytest-parametrize-names-wrong-type (PT006)
Avoid the type of parameter names passed to `pytest.mark.parametrize`.

### pytest-parametrize-values-wrong-type (PT007)
Avoid the type of parameter values passed to `pytest.mark.parametrize`.

### pytest-patch-with-lambda (PT008)
Avoid mocked calls that use a dummy `lambda` function instead of `return_value`.
❌ 
```
def test_foo(mocker):
    mocker.patch("module.target", lambda x, y: 7)
```
✅ 
```
def test_foo(mocker):
    mocker.patch("module.target", return_value=7)
    # If the lambda makes use of the arguments, no diagnostic is emitted.
    mocker.patch("module.other_target", lambda x, y: x)
```

### pytest-raises-too-broad (PT011)
Avoid `pytest.raises` calls without a `match` or `check` parameter.
❌ 
```
import pytest
def test_foo():
    with pytest.raises(ValueError):
        ...
    # empty string is also an error
    with pytest.raises(ValueError, match=""):
…
```
✅ 
```
import pytest
def test_foo():
    with pytest.raises(ValueError, match="expected message"):
        ...
```

### pytest-raises-with-multiple-statements (PT012)
Avoid `pytest.raises` context managers with multiple statements.
❌ 
```
import pytest
def test_foo():
    with pytest.raises(MyError):
        setup()
        func_to_test()  # not executed if `setup()` raises `MyError`
        assert foo()  # not executed
```
✅ 
```
import pytest
def test_foo():
    setup()
    with pytest.raises(MyError):
        func_to_test()
    assert foo()
```

### pytest-raises-without-exception (PT010)
Avoid `pytest.raises` calls without an expected exception.
❌ 
```
import pytest
def test_foo():
    with pytest.raises():
        do_something()
```
✅ 
```
import pytest
def test_foo():
    with pytest.raises(SomeException):
        do_something()
```

### pytest-unittest-assertion (PT009)
Avoid uses of assertion methods from the `unittest` module.
❌ 
```
import unittest
class TestFoo(unittest.TestCase):
    def test_foo(self):
        self.assertEqual(a, b)
```
✅ 
```
import unittest
class TestFoo(unittest.TestCase):
    def test_foo(self):
        assert a == b
```

### pytest-unittest-raises-assertion (PT027)
Avoid uses of exception-related assertion methods from the `unittest` module.
❌ 
```
import unittest
class TestFoo(unittest.TestCase):
    def test_foo(self):
        with self.assertRaises(ValueError):
            raise ValueError("foo")
```
✅ 
```
import unittest
import pytest
class TestFoo(unittest.TestCase):
    def test_foo(self):
        with pytest.raises(ValueError):
            raise ValueError("foo")
```

### pytest-unnecessary-asyncio-mark-on-fixture (PT024)
Avoid unnecessary `@pytest.mark.asyncio` decorators applied to fixtures.
❌ 
```
import pytest
@pytest.mark.asyncio()
@pytest.fixture()
async def my_fixture():
    return 0
```
✅ 
```
import pytest
@pytest.fixture()
async def my_fixture():
    return 0
```

### pytest-use-fixtures-without-parameters (PT026)
Avoid `@pytest.mark.usefixtures()` decorators that aren't passed any arguments.
❌ 
```
import pytest
@pytest.mark.usefixtures()
def test_something(): ...
```
✅ `def test_something(): ...`

### pytest-useless-yield-fixture (PT022)
Avoid unnecessary `yield` expressions in `pytest` fixtures.
❌ 
```
import pytest
@pytest.fixture()
def my_fixture():
    resource = acquire_resource()
    yield resource
```
✅ 
```
import pytest
@pytest.fixture()
def my_fixture_with_teardown():
    resource = acquire_resource()
    yield resource
    resource.release()
…
```

### pytest-warns-too-broad (PT030)
Avoid `pytest.warns` calls without a `match` parameter.
❌ 
```
import pytest
def test_foo():
    with pytest.warns(Warning):
        ...
    # empty string is also an error
    with pytest.warns(Warning, match=""):
…
```
✅ 
```
import pytest
def test_foo():
    with pytest.warns(Warning, match="expected message"):
        ...
```

### pytest-warns-with-multiple-statements (PT031)
Avoid `pytest.warns` context managers with multiple statements.
❌ 
```
import pytest
def test_foo_warns():
    with pytest.warns(Warning):
        setup()  # False negative if setup triggers a warning but foo does not.
        foo()
```
✅ 
```
import pytest
def test_foo_warns():
    setup()
    with pytest.warns(Warning):
        foo()
```

### pytest-warns-without-warning (PT029)
Avoid `pytest.warns` calls without an expected warning.
❌ 
```
import pytest
def test_foo():
    with pytest.warns():
        do_something()
```
✅ 
```
import pytest
def test_foo():
    with pytest.warns(SomeWarning):
        do_something()
```

### Plugin: `flake8-raise`

### unnecessary-paren-on-raise-exception (RSE102)
Avoid unnecessary parentheses on raised exceptions.
❌ `raise TypeError()`
✅ `raise TypeError`

### Plugin: `flake8-return`

### implicit-return (RET503)
Avoid missing explicit `return` statements at the end of functions that can return non-`None` values.
❌ 
```
def foo(bar):
    if not bar:
        return 1
```
✅ 
```
def foo(bar):
    if not bar:
        return 1
    return None
```

### implicit-return-value (RET502)
Avoid the presence of a `return` statement with no explicit value, for functions that return non-`None` values elsewhere.
❌ 
```
def foo(bar):
    if not bar:
        return
    return 1
```
✅ 
```
def foo(bar):
    if not bar:
        return None
    return 1
```

### superfluous-else-break (RET508)
Avoid `else` statements with a `break` statement in the preceding `if` block.
❌ 
```
def foo(bar, baz):
    for i in bar:
        if i > baz:
            break
        else:
            x = 0
```
✅ 
```
def foo(bar, baz):
    for i in bar:
        if i > baz:
            break
        x = 0
```

### superfluous-else-continue (RET507)
Avoid `else` statements with a `continue` statement in the preceding `if` block.
❌ 
```
def foo(bar, baz):
    for i in bar:
        if i < baz:
            continue
        else:
            x = 0
```
✅ 
```
def foo(bar, baz):
    for i in bar:
        if i < baz:
            continue
        x = 0
```

### superfluous-else-raise (RET506)
Avoid `else` statements with a `raise` statement in the preceding `if` block.
❌ 
```
def foo(bar, baz):
    if bar == "Specific Error":
        raise Exception(bar)
    else:
        raise Exception(baz)
```
✅ 
```
def foo(bar, baz):
    if bar == "Specific Error":
        raise Exception(bar)
    raise Exception(baz)
```

### superfluous-else-return (RET505)
Avoid `else` statements with a `return` statement in the preceding `if` block.
❌ 
```
def foo(bar, baz):
    if bar:
        return 1
    else:
        return baz
```
✅ 
```
def foo(bar, baz):
    if bar:
        return 1
    return baz
```

### unnecessary-assign (RET504)
Avoid variable assignments that immediately precede a `return` of the assigned variable.
❌ 
```
def foo():
    bar = 1
    return bar
```
✅ 
```
def foo():
    return 1
```

### unnecessary-return-none (RET501)
Avoid the presence of a `return None` statement when `None` is the only possible return value.
❌ 
```
def foo(bar):
    if not bar:
        return
    return None
```
✅ 
```
def foo(bar):
    if not bar:
        return
    return
```

### Plugin: `flake8-self`

### private-member-access (SLF001)
Avoid accesses on "private" class members.
❌ 
```
class Class:
    def __init__(self):
        self._private_member = "..."
var = Class()
print(var._private_member)
```
✅ 
```
class Class:
    def __init__(self):
        self.public_member = "..."
var = Class()
print(var.public_member)
```

### Plugin: `flake8-simplify`

### collapsible-if (SIM102)
Avoid nested `if` statements that can be collapsed into a single `if` statement.
❌ 
```
if foo:
    if bar:
        ...
```
✅ 
```
if foo and bar:
    ...
```

### compare-with-tuple (SIM109)
Avoid boolean expressions that contain multiple equality comparisons to the same value.
❌ 
```
if foo == x or foo == y:
    ...
```
✅ 
```
if foo in (x, y):
    ...
```

### dict-get-with-none-default (SIM910)
Avoid `dict.get()` calls that pass `None` as the default value.
❌ 
```
ages = {"Tom": 23, "Maria": 23, "Dog": 11}
age = ages.get("Cat", None)
```
✅ 
```
ages = {"Tom": 23, "Maria": 23, "Dog": 11}
age = ages.get("Cat")
```

### double-negation (SIM208)
Avoid double negations (i.e., multiple `not` operators).
❌ `not (not a)`
✅ `a`

### duplicate-isinstance-call (SIM101)
Avoid multiple `isinstance` calls on the same target.
❌ 
```
if isinstance(obj, int) or isinstance(obj, float):
    pass
```
✅ 
```
if isinstance(obj, (int, float)):
    pass
```

### enumerate-for-loop (SIM113)
Avoid `for` loops with explicit loop-index variables that can be replaced with `enumerate()`.
❌ 
```
fruits = ["apple", "banana", "cherry"]
i = 0
for fruit in fruits:
    print(f"{i + 1}. {fruit}")
    i += 1
```
✅ 
```
fruits = ["apple", "banana", "cherry"]
for i, fruit in enumerate(fruits):
    print(f"{i + 1}. {fruit}")
```

### expr-and-false (SIM223)
Avoid `and` expressions that contain falsey values.
❌ 
```
if x and [] and y:
    pass
a = x and [] and y
```
✅ 
```
if False:
    pass
a = x and []
```

### expr-and-not-expr (SIM220)
Avoid `and` expressions that include both an expression and its negation.
❌ `x and not x`

### expr-or-not-expr (SIM221)
Avoid `or` expressions that include both an expression and its negation.
❌ `x or not x`

### expr-or-true (SIM222)
Avoid `or` expressions that contain truthy values.
❌ 
```
if x or [1] or y:
    pass
a = x or [1] or y
```
✅ 
```
if True:
    pass
a = x or [1]
```

### if-else-block-instead-of-dict-get (SIM401)
Avoid `if` statements that can be replaced with `dict.get` calls.
❌ 
```
foo = {}
if "bar" in foo:
    value = foo["bar"]
else:
    value = 0
```
✅ 
```
foo = {}
value = foo.get("bar", 0)
```

### if-else-block-instead-of-dict-lookup (SIM116)
Avoid three or more consecutive if-statements with direct returns
❌ 
```
def find_phrase(x):
    if x == 1:
        return "Hello"
    elif x == 2:
        return "Goodbye"
    elif x == 3:
…
```
✅ 
```
def find_phrase(x):
    phrases = {1: "Hello", 2: "Goodye", 3: "Good morning"}
    return phrases.get(x, "Goodnight")
```

### if-else-block-instead-of-if-exp (SIM108)
Avoid `if`-`else`-blocks that can be replaced with a ternary or binary operator.
❌ 
```
if foo:
    bar = x
else:
    bar = y
```
✅ `bar = x if foo else y`

### if-expr-with-false-true (SIM211)
Avoid `if` expressions that can be replaced by negating a given condition.
❌ `False if a else True`
✅ `not a`

### if-expr-with-true-false (SIM210)
Avoid `if` expressions that can be replaced with `bool()` calls.
❌ `True if a else False`
✅ `bool(a)`

### if-expr-with-twisted-arms (SIM212)
Avoid `if` expressions that check against a negated condition.
❌ `b if not a else a`
✅ `a if a else b`

### if-with-same-arms (SIM114)
Avoid `if` branches with identical arm bodies.
❌ 
```
if x == 1:
    print("Hello")
elif x == 2:
    print("Hello")
```
✅ 
```
if x == 1 or x == 2:
    print("Hello")
```

### in-dict-keys (SIM118)
Avoid key-existence checks against `dict.keys()` calls.
❌ `key in foo.keys()`
✅ `key in foo`

### multiple-with-statements (SIM117)
Avoid the unnecessary nesting of multiple consecutive context managers.
❌ 
```
with A() as a:
    with B() as b:
        pass
```
✅ 
```
with A() as a, B() as b:
    pass
```

### needless-bool (SIM103)
Avoid `if` statements that can be replaced with `bool`.
❌ 
```
def foo(x: int) -> bool:
    if x > 0:
        return True
    else:
        return False
```
✅ 
```
def foo(x: int) -> bool:
    return x > 0
```

### negate-equal-op (SIM201)
Avoid negated `==` operators.
❌ `not a == b`
✅ `a != b`

### negate-not-equal-op (SIM202)
Avoid negated `!=` operators.
❌ `not a != b`
✅ `a == b`

### open-file-with-context-handler (SIM115)
Avoid cases where files are opened (e.g., using the builtin `open()` function) without using a context manager.
❌ 
```
file = open("foo.txt")
...
file.close()
```
✅ 
```
with open("foo.txt") as file:
    ...
```

### reimplemented-builtin (SIM110)
Avoid `for` loops that can be replaced with a builtin function, like `any` or `all`.
❌ 
```
def foo():
    for item in iterable:
        if predicate(item):
            return True
    return False
```
✅ 
```
def foo():
    return any(predicate(item) for item in iterable)
```

### return-in-try-except-finally (SIM107)
Avoid `return` statements in `try`-`except` and `finally` blocks.
❌ 
```
def squared(n):
    try:
        sqr = n**2
        return sqr
    except Exception:
        return "An exception occurred"
…
```
✅ 
```
def squared(n):
    try:
        return_value = n**2
    except Exception:
        return_value = "An exception occurred"
    finally:
…
```

### split-static-string (SIM905)
Avoid static `str.split` calls that can be replaced with list literals.
❌ `"a,b,c,d".split(",")`
✅ `["a", "b", "c", "d"]`

### suppressible-exception (SIM105)
Avoid `try`-`except`-`pass` blocks that can be replaced with the `contextlib.suppress` context manager.
❌ 
```
try:
    1 / 0
except ZeroDivisionError:
    pass
```
✅ 
```
import contextlib
with contextlib.suppress(ZeroDivisionError):
    1 / 0
```

### uncapitalized-environment-variables (SIM112)
Avoid environment variables that are not capitalized.
❌ 
```
import os
os.environ["foo"]
```
✅ 
```
import os
os.environ["FOO"]
```

### yoda-conditions (SIM300)
Avoid conditions that position a constant on the left-hand side of the comparison operator, rather than the right-hand side.
❌ 
```
if "Foo" == foo:
    ...
```
✅ 
```
if foo == "Foo":
    ...
```

### zip-dict-keys-and-values (SIM911)
Avoid use of `zip()` to iterate over keys and values of a dictionary at once.
❌ 
```
flag_stars = {"USA": 50, "Slovenia": 3, "Panama": 2, "Australia": 6}
for country, stars in zip(flag_stars.keys(), flag_stars.values()):
    print(f"{country}'s flag has {stars} stars.")
```
✅ 
```
flag_stars = {"USA": 50, "Slovenia": 3, "Panama": 2, "Australia": 6}
for country, stars in flag_stars.items():
    print(f"{country}'s flag has {stars} stars.")
```

### Plugin: `flake8-slots`

### no-slots-in-namedtuple-subclass (SLOT002)
Avoid subclasses of `collections.namedtuple` or `typing.NamedTuple` that lack a `__slots__` definition.
❌ 
```
from collections import namedtuple
class Foo(namedtuple("foo", ["str", "int"])):
    pass
```
✅ 
```
from collections import namedtuple
class Foo(namedtuple("foo", ["str", "int"])):
    __slots__ = ()
```

### no-slots-in-str-subclass (SLOT000)
Avoid subclasses of `str` that lack a `__slots__` definition.
❌ 
```
class Foo(str):
    pass
```
✅ 
```
class Foo(str):
    __slots__ = ()
```

### no-slots-in-tuple-subclass (SLOT001)
Avoid subclasses of `tuple` that lack a `__slots__` definition.
❌ 
```
class Foo(tuple):
    pass
```
✅ 
```
class Foo(tuple):
    __slots__ = ()
```

### Plugin: `flynt`

### static-join-to-f-string (FLY002)
Avoid `str.join` calls that can be replaced with f-strings.
❌ `" ".join((foo, bar))`
✅ `f"{foo} {bar}"`

### Plugin: `pygrep-hooks`

### blanket-noqa (PGH004)
Avoid `noqa` annotations that suppress all diagnostics, as opposed to targeting specific diagnostics.
❌ `from .base import *  # noqa`
✅ `from .base import *  # noqa: F403`

### blanket-type-ignore (PGH003)
Avoid `type: ignore` annotations that suppress all type warnings, as opposed to targeting specific type warnings.
❌ `from foo import secrets  # type: ignore`
✅ `from foo import secrets  # type: ignore[attr-defined]`

### deprecated-log-warn (PGH002)
Avoid usages of the deprecated `warn` method from the `logging` module.
❌ 
```
import logging
def foo():
    logging.warn("Something happened")
```
✅ 
```
import logging
def foo():
    logging.warning("Something happened")
```

### eval (PGH001)
Avoid uses of the builtin `eval()` function.
❌ 
```
def foo():
    x = eval(input("Enter a number: "))
    ...
```
✅ 
```
def foo():
    x = input("Enter a number: ")
    ...
```

### invalid-mock-access (PGH005)
Avoid common mistakes when using mock objects.
❌ `my_mock.assert_called`
✅ `my_mock.assert_called()`

### Plugin: `refurb`

### bit-count (FURB161)
Avoid uses of `bin(...).count("1")` to perform a population count.
❌ 
```
x = bin(123).count("1")
y = bin(0b1111011).count("1")
```
✅ 
```
x = (123).bit_count()
y = 0b1111011.bit_count()
```

### check-and-remove-from-set (FURB132)
Avoid uses of `set.remove` that can be replaced with `set.discard`.
❌ 
```
nums = {123, 456}
if 123 in nums:
    nums.remove(123)
```
✅ 
```
nums = {123, 456}
nums.discard(123)
```

### delete-full-slice (FURB131)
Avoid `del` statements that delete the entire slice of a list or dictionary.
❌ 
```
names = {"key": "value"}
nums = [1, 2, 3]
del names[:]
del nums[:]
```
✅ 
```
names = {"key": "value"}
nums = [1, 2, 3]
names.clear()
nums.clear()
```

### f-string-number-format (FURB116)
Avoid uses of `bin(...)[2:]` (or `hex`, or `oct`) to convert an integer into a string.
❌ `print(bin(1337)[2:])`
✅ `print(f"{1337:b}")`

### for-loop-set-mutations (FURB142)
Avoid code that updates a set with the contents of an iterable by using a `for` loop to call `.add()` or `.discard()` on each element separately.
❌ 
```
s = set()
for x in (1, 2, 3):
    s.add(x)
for x in (1, 2, 3):
    s.discard(x)
```
✅ 
```
s = set()
s.update((1, 2, 3))
s.difference_update((1, 2, 3))
```

### for-loop-writes (FURB122)
Avoid the use of `IOBase.write` in a for loop.
❌ 
```
from pathlib import Path
with Path("file").open("w") as f:
    for line in lines:
        f.write(line)
with Path("file").open("wb") as f_b:
    for line_b in lines_b:
…
```
✅ 
```
from pathlib import Path
with Path("file").open("w") as f:
    f.writelines(lines)
with Path("file").open("wb") as f_b:
    f_b.writelines(line_b.encode() for line_b in lines_b)
```

### fromisoformat-replace-z (FURB162)
Avoid `datetime.fromisoformat()` calls where the only argument is an inline replacement of `Z` with a zero offset timezone.
❌ 
```
from datetime import datetime
date = "2025-01-01T00:00:00Z"
datetime.fromisoformat(date.replace("Z", "+00:00"))
datetime.fromisoformat(date[:-1] + "-00")
datetime.fromisoformat(date.strip("Z", "-0000"))
datetime.fromisoformat(date.rstrip("Z", "-00:00"))
```
✅ 
```
from datetime import datetime
date = "2025-01-01T00:00:00Z"
datetime.fromisoformat(date)
```

### hardcoded-string-charset (FURB156)
Avoid uses of hardcoded charsets, which are defined in Python string module.
❌ 
```
x = "0123456789"
y in "abcdefghijklmnopqrstuvwxyz"
```

### hashlib-digest-hex (FURB181)
Avoid the use of `.digest().hex()` on a hashlib hash, like `sha512`.
❌ 
```
from hashlib import sha512
hashed = sha512(b"some data").digest().hex()
```
✅ 
```
from hashlib import sha512
hashed = sha512(b"some data").hexdigest()
```

### if-exp-instead-of-or-operator (FURB110)
Avoid ternary `if` expressions that can be replaced with the `or` operator.
❌ 
```
x, y = 1, 2
z = x if x else y
```
✅ 
```
x, y = 1, 2
z = x or y
```

### if-expr-min-max (FURB136)
Avoid `if` expressions that can be replaced with `min()` or `max()` calls.
❌ 
```
score1, score2 = 4, 5
highest_score = score1 if score1 > score2 else score2
```
✅ 
```
score1, score2 = 4, 5
highest_score = max(score2, score1)
```

### implicit-cwd (FURB177)
Avoid current-directory lookups using `Path().resolve()`.
❌ 
```
from pathlib import Path
cwd = Path().resolve()
```
✅ 
```
from pathlib import Path
cwd = Path.cwd()
```

### int-on-sliced-str (FURB166)
Avoid uses of `int` with an explicit base in which a string expression is stripped of its leading prefix (i.e., `0b`, `0o`, or `0x`).
❌ 
```
num = "0xABC"
if num.startswith("0b"):
    i = int(num[2:], 2)
elif num.startswith("0o"):
    i = int(num[2:], 8)
elif num.startswith("0x"):
…
```
✅ 
```
num = "0xABC"
i = int(num, 0)
print(i)
```

### isinstance-type-none (FURB168)
Avoid uses of `isinstance` that check if an object is of type `None`.
❌ `isinstance(obj, type(None))`
✅ `obj is None`

### list-reverse-copy (FURB187)
Avoid list reversals that can be performed in-place in lieu of creating a new list.
❌ 
```
l = [1, 2, 3]
l = reversed(l)
l = [1, 2, 3]
l = list(reversed(l))
l = [1, 2, 3]
l = l[::-1]
```
✅ 
```
l = [1, 2, 3]
l.reverse()
```

### math-constant (FURB152)
Avoid literals that are similar to constants in `math` module.
❌ `A = 3.141592 * r**2`
✅ `A = math.pi * r**2`

### meta-class-abc-meta (FURB180)
Avoid uses of `metaclass=abc.ABCMeta` to define abstract base classes (ABCs).
❌ 
```
import abc
class C(metaclass=abc.ABCMeta):
    pass
```
✅ 
```
import abc
class C(abc.ABC):
    pass
```

### print-empty-string (FURB105)
Avoid `print` calls with unnecessary empty strings as positional arguments and unnecessary `sep` keyword arguments.
❌ `print("")`
✅ `print()`

### read-whole-file (FURB101)
Avoid uses of `open` and `read` that can be replaced by `pathlib` methods, like `Path.read_text` and `Path.read_bytes`.
❌ 
```
with open("file.txt") as f:
    contents = f.read()
```
✅ 
```
from pathlib import Path
contents = Path("file.txt").read_text()
```

### readlines-in-for (FURB129)
Avoid uses of `readlines()` when iterating over a file line-by-line.
❌ 
```
with open("file.txt") as fp:
    for line in fp.readlines():
        ...
```
✅ 
```
with open("file.txt") as fp:
    for line in fp:
        ...
```

### redundant-log-base (FURB163)
Avoid `math.log` calls with a redundant base.
❌ 
```
import math
math.log(4, math.e)
math.log(4, 2)
math.log(4, 10)
```
✅ 
```
import math
math.log(4)
math.log2(4)
math.log10(4)
```

### regex-flag-alias (FURB167)
Avoid the use of shorthand aliases for regular expression flags (e.g., `re.I` instead of `re.IGNORECASE`).
❌ 
```
import re
if re.search("^hello", "hello world", re.I):
    ...
```
✅ 
```
import re
if re.search("^hello", "hello world", re.IGNORECASE):
    ...
```

### reimplemented-operator (FURB118)
Avoid lambda expressions and function definitions that can be replaced with a function from the `operator` module.
❌ 
```
import functools
nums = [1, 2, 3]
total = functools.reduce(lambda x, y: x + y, nums)
```
✅ 
```
import functools
import operator
nums = [1, 2, 3]
total = functools.reduce(operator.add, nums)
```

### reimplemented-starmap (FURB140)
Avoid generator expressions, list and set comprehensions that can be replaced with `itertools.starmap`.
❌ `all(predicate(a, b) for a, b in some_iterable)`
✅ 
```
from itertools import starmap
all(starmap(predicate, some_iterable))
```

### repeated-append (FURB113)
Avoid consecutive calls to `append`.
❌ 
```
nums = [1, 2, 3]
nums.append(4)
nums.append(5)
nums.append(6)
```
✅ 
```
nums = [1, 2, 3]
nums.extend((4, 5, 6))
```

### repeated-global (FURB154)
Avoid consecutive `global` (or `nonlocal`) statements.
❌ 
```
def func():
    global x
    global y
    print(x, y)
```
✅ 
```
def func():
    global x, y
    print(x, y)
```

### single-item-membership-test (FURB171)
Avoid membership tests against single-item containers.
❌ `1 in [1]`
✅ `1 == 1`

### slice-copy (FURB145)
Avoid unbounded slice expressions to copy a list.
❌ 
```
a = [1, 2, 3]
b = a[:]
```
✅ 
```
a = [1, 2, 3]
b = a.copy()
```

### slice-to-remove-prefix-or-suffix (FURB188)
Avoid code that could be written more idiomatically using `str.removeprefix()` or `str.removesuffix()`.
❌ 
```
def example(filename: str, text: str):
    filename = filename[:-4] if filename.endswith(".txt") else filename
    if text.startswith("pre"):
        text = text[3:]
```
✅ 
```
def example(filename: str, text: str):
    filename = filename.removesuffix(".txt")
    text = text.removeprefix("pre")
```

### sorted-min-max (FURB192)
Avoid uses of `sorted()` to retrieve the minimum or maximum value in a sequence.
❌ 
```
nums = [3, 1, 4, 1, 5]
lowest = sorted(nums)[0]
highest = sorted(nums)[-1]
highest = sorted(nums, reverse=True)[0]
```
✅ 
```
nums = [3, 1, 4, 1, 5]
lowest = min(nums)
highest = max(nums)
```

### subclass-builtin (FURB189)
Avoid subclasses of `dict`, `list` or `str`.
❌ 
```
class UppercaseDict(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key.upper(), value)
d = UppercaseDict({"a": 1, "b": 2})  # Bypasses __setitem__
print(d)  # {'a': 1, 'b': 2}
```
✅ 
```
from collections import UserDict
class UppercaseDict(UserDict):
    def __setitem__(self, key, value):
        super().__setitem__(key.upper(), value)
d = UppercaseDict({"a": 1, "b": 2})  # Uses __setitem__
print(d)  # {'A': 1, 'B': 2}
```

### type-none-comparison (FURB169)
Avoid uses of `type` that compare the type of an object to the type of `None`.
❌ `type(obj) is type(None)`
✅ `obj is None`

### unnecessary-enumerate (FURB148)
Avoid uses of `enumerate` that discard either the index or the value when iterating over a sequence.
❌ 
```
for index, _ in enumerate(sequence):
    print(index)
for _, value in enumerate(sequence):
    print(value)
```
✅ 
```
for index in range(len(sequence)):
    print(index)
for value in sequence:
    print(value)
```

### unnecessary-from-float (FURB164)
Avoid unnecessary `from_float` and `from_decimal` usages to construct `Decimal` and `Fraction` instances.
❌ 
```
from decimal import Decimal
from fractions import Fraction
Decimal.from_float(4.2)
Decimal.from_float(float("inf"))
Fraction.from_float(4.2)
Fraction.from_decimal(Decimal("4.2"))
```
✅ 
```
from decimal import Decimal
from fractions import Fraction
Decimal(4.2)
Decimal("inf")
Fraction(4.2)
Fraction(Decimal("4.2"))
```

### verbose-decimal-constructor (FURB157)
Avoid unnecessary string literal or float casts in `Decimal` constructors.
❌ 
```
from decimal import Decimal
Decimal("0")
Decimal(float("Infinity"))
```
✅ 
```
from decimal import Decimal
Decimal(0)
Decimal("Infinity")
```

### write-whole-file (FURB103)
Avoid uses of `open` and `write` that can be replaced by `pathlib` methods, like `Path.write_text` and `Path.write_bytes`.
❌ 
```
with open("file.txt", "w") as f:
    f.write("some text")
```
✅ 
```
from pathlib import Path
Path("file.txt").write_text("some text")
```

### Plugin: `ruff`

### access-annotations-from-class-dict (RUF063)
Avoid uses of `foo.__dict__.get("__annotations__")` or `foo.__dict__["__annotations__"]` on Python 3.10+ and Python < 3.10 when typing-extensions is enabled.

### ambiguous-unicode-character-comment (RUF003)
Avoid ambiguous Unicode characters in comments.
❌ `foo()  # nоqa  # "о" is Cyrillic (`U+043E`)`
✅ `foo()  # noqa  # "o" is Latin (`U+006F`)`

### ambiguous-unicode-character-docstring (RUF002)
Avoid ambiguous Unicode characters in docstrings.
❌ `"""A lovely docstring (with a `U+FF09` parenthesis）."""`
✅ `"""A lovely docstring (with no strange parentheses)."""`

### ambiguous-unicode-character-string (RUF001)
Avoid ambiguous Unicode characters in strings.
❌ `print("Ηello, world!")  # "Η" is the Greek eta (`U+0397`).`
✅ `print("Hello, world!")  # "H" is the Latin capital H (`U+0048`).`

### assert-with-print-message (RUF030)
Avoid uses of `assert expression, print(message)`.
❌ `assert False, print("This is a message")`
✅ `assert False, "This is a message"`

### assignment-in-assert (RUF018)
Avoid named assignment expressions (e.g., `x := 0`) in `assert` statements.
❌ 
```
assert (x := 0) == 0
print(x)
```
✅ 
```
x = 0
assert x == 0
print(x)
```

### asyncio-dangling-task (RUF006)
Avoid `asyncio.create_task` and `asyncio.ensure_future` calls that do not store a reference to the returned result.
❌ 
```
import asyncio
for i in range(10):
    # This creates a weak reference to the task, which may be garbage
    # collected at any time.
    asyncio.create_task(some_coro(param=i))
```
✅ 
```
import asyncio
background_tasks = set()
for i in range(10):
    task = asyncio.create_task(some_coro(param=i))
    # Add task to the set. This creates a strong reference.
    background_tasks.add(task)
…
```

### class-with-mixed-type-vars (RUF053)
Avoid classes that have PEP 695 while also inheriting from `typing.Generic` or `typing_extensions.Generic`.
❌ 
```
from typing import Generic, ParamSpec, TypeVar, TypeVarTuple
U = TypeVar("U")
P = ParamSpec("P")
Ts = TypeVarTuple("Ts")
class C[T](Generic[U, P, *Ts]): ...
```
✅ `class C[T, U, **P, *Ts]: ...`

### collection-literal-concatenation (RUF005)
Avoid uses of the `+` operator to concatenate collections.
❌ 
```
foo = [2, 3, 4]
bar = [1] + foo + [5, 6]
```
✅ 
```
foo = [2, 3, 4]
bar = [1, *foo, 5, 6]
```

### dataclass-enum (RUF049)
Avoid enum classes which are also decorated with `@dataclass`.
❌ 
```
from dataclasses import dataclass
from enum import Enum
@dataclass
class E(Enum): ...
```
✅ 
```
from enum import Enum
class E(Enum): ...
```

### decimal-from-float-literal (RUF032)
Avoid `Decimal` calls passing a float literal.
❌ `num = Decimal(1.2345)`
✅ `num = Decimal("1.2345")`

### default-factory-kwarg (RUF026)
Avoid incorrect usages of `default_factory` as a keyword argument when initializing a `defaultdict`.
❌ 
```
defaultdict(default_factory=int)
defaultdict(default_factory=list)
```
✅ 
```
defaultdict(int)
defaultdict(list)
```

### duplicate-entry-in-dunder-all (RUF068)
Avoid duplicate elements in `__all__` definitions.
❌ 
```
__all__ = [
    "DatabaseConnection",
    "Product",
    "User",
    "DatabaseConnection",  # Duplicate
]
```
✅ 
```
__all__ = [
    "DatabaseConnection",
    "Product",
    "User",
]
```

### explicit-f-string-type-conversion (RUF010)
Avoid uses of `str()`, `repr()`, and `ascii()` as explicit type conversions within f-strings.
❌ 
```
a = "some string"
f"{repr(a)}"
```
✅ 
```
a = "some string"
f"{a!r}"
```

### f-string-percent-format (RUF073)
Avoid uses of the `%` operator on f-strings.
❌ 
```
f"{name}" % name
f"hello %s %s" % (first, second)
```
✅ 
```
f"{name}"
f"hello {first} {second}"
```

### falsy-dict-get-fallback (RUF056)
Avoid `dict.get(key, falsy_value)` calls in boolean test positions.
❌ 
```
if dict.get(key, False):
    ...
```
✅ 
```
if dict.get(key):
    ...
```

### float-equality-comparison (RUF069)
Avoid comparisons between floating-point values using `==` or `!=`.
❌ 
```
assert 0.1 + 0.2 == 0.3  # AssertionError
assert complex(0.3, 0.1) == complex(0.1 + 0.2, 0.1)  # AssertionError
```

### function-call-in-dataclass-default-argument (RUF009)
Avoid function calls in dataclass attribute defaults.
❌ 
```
from dataclasses import dataclass
def simple_list() -> list[int]:
    return [1, 2, 3, 4]
@dataclass
class A:
    mutable_default: list[int] = simple_list()
```
✅ 
```
from dataclasses import dataclass, field
def creating_list() -> list[int]:
    return [1, 2, 3, 4]
@dataclass
class A:
    mutable_default: list[int] = field(default_factory=creating_list)
```

### if-key-in-dict-del (RUF051)
Avoid `if key in dictionary: del dictionary[key]`.
❌ 
```
if key in dictionary:
    del dictionary[key]
```
✅ `dictionary.pop(key, None)`

### implicit-class-var-in-dataclass (RUF045)
Avoid implicit class variables in dataclasses.
❌ 
```
@dataclass
class C:
    a = 1
```
✅ 
```
from typing import ClassVar
@dataclass
class C:
    a: ClassVar[int] = 1
```

### implicit-optional (RUF013)
Avoid the use of implicit `Optional` in type annotations when the default parameter value is `None`.
❌ 
```
def foo(arg: int = None):
    pass
```
✅ 
```
from typing import Optional
def foo(arg: Optional[int] = None):
    pass
```

### in-empty-collection (RUF060)
Avoid membership tests on empty collections (such as `list`, `tuple`, `set`, or `dict`).
❌ 
```
if 1 not in set():
    print("got it!")
```
✅ `print("got it!")`

### incorrectly-parenthesized-tuple-in-subscript (RUF031)
Avoid consistent style regarding whether nonempty tuples in subscripts are parenthesized.
❌ 
```
directions = {(0, 1): "North", (1, 0): "East", (0, -1): "South", (-1, 0): "West"}
directions[(0, 1)]
```

### indented-form-feed (RUF054)
Avoid form feed characters preceded by either a space or a tab.
❌ `if foo():\n    \fbar()`
✅ `if foo():\n    bar()`

### invalid-assert-message-literal-argument (RUF040)
Avoid invalid use of literals in assert message arguments.
❌ 
```
fruits = ["apples", "plums", "pears"]
fruits.filter(lambda fruit: fruit.startwith("p"))
assert len(fruits), 2  # True unless the list is empty
```
✅ 
```
fruits = ["apples", "plums", "pears"]
fruits.filter(lambda fruit: fruit.startwith("p"))
assert len(fruits) == 2
```

### invalid-formatter-suppression-comment (RUF028)
Avoid formatter suppression comments that are ineffective or incompatible with Ruff's formatter.

### invalid-index-type (RUF016)
Avoid indexed access to lists, strings, tuples, bytes, and comprehensions using a type other than an integer or slice.
❌ `var = [1, 2, 3]["x"]`
✅ `var = [1, 2, 3][0]`

### invalid-pyproject-toml (RUF200)
Avoid any pyproject.toml that does not conform to the schema from the relevant PEPs.
❌ 
```
[project]
name = "crab"
version = "1.0.0"
authors = ["Ferris the Crab <[email protected]>"]
```
✅ 
```
[project]
name = "crab"
version = "1.0.0"
authors = [
  { name = "Ferris the Crab", email = "[email protected]" }
]
```

### invalid-rule-code (RUF102)
Avoid `noqa` codes that are invalid.
❌ `import os  # noqa: XYZ999`
✅ `import os`

### invalid-suppression-comment (RUF103)
Avoid invalid suppression comments

### legacy-form-pytest-raises (RUF061)
Avoid non-context-manager use of `pytest.raises`, `pytest.warns`, and `pytest.deprecated_call`.
❌ 
```
import pytest
excinfo = pytest.raises(ValueError, int, "hello")
pytest.warns(UserWarning, my_function, arg)
pytest.deprecated_call(my_deprecated_function, arg1, arg2)
```
✅ 
```
import pytest
with pytest.raises(ValueError) as excinfo:
    int("hello")
with pytest.warns(UserWarning):
    my_function(arg)
with pytest.deprecated_call():
…
```

### logging-eager-conversion (RUF065)
Avoid eager string conversion of arguments to `logging` calls.
❌ 
```
import logging
logging.basicConfig(format="%(message)s", level=logging.INFO)
user = "Maria"
logging.info("%s - Something happened", str(user))
```
✅ 
```
import logging
logging.basicConfig(format="%(message)s", level=logging.INFO)
user = "Maria"
logging.info("%s - Something happened", user)
```

### map-int-version-parsing (RUF048)
Avoid calls of the form `map(int, __version__.split("."))`.
❌ `tuple(map(int, matplotlib.__version__.split(".")))`
✅ 
```
import packaging.version as version
version.parse(matplotlib.__version__)
```

### missing-f-string-syntax (RUF027)
Searches for strings that look like they were meant to be f-strings, but are missing an `f` prefix.
❌ 
```
name = "Sarah"
day_of_week = "Tuesday"
print("Hello {name}! It is {day_of_week} today!")
```
✅ 
```
name = "Sarah"
day_of_week = "Tuesday"
print(f"Hello {name}! It is {day_of_week} today!")
```

### mutable-class-default (RUF012)
Avoid mutable default values in class attributes.
❌ 
```
class A:
    variable_1: list[int] = []
    variable_2: set[int] = set()
    variable_3: dict[str, int] = {}
```
✅ 
```
class A:
    def __init__(self) -> None:
        self.variable_1: list[int] = []
        self.variable_2: set[int] = set()
        self.variable_3: dict[str, int] = {}
```

### mutable-dataclass-default (RUF008)
Avoid mutable default values in dataclass attributes.
❌ 
```
from dataclasses import dataclass
@dataclass
class A:
    # A list without a `default_factory` or `ClassVar` annotation
    # will raise a `ValueError`.
    mutable_default: list[int] = []
```
✅ 
```
from dataclasses import dataclass, field
@dataclass
class A:
    mutable_default: list[int] = field(default_factory=list)
```

### mutable-fromkeys-value (RUF024)
Avoid mutable objects passed as a value argument to `dict.fromkeys`.
❌ 
```
cities = dict.fromkeys(["UK", "Poland"], [])
cities["UK"].append("London")
cities["Poland"].append("Poznan")
print(cities)  # {'UK': ['London', 'Poznan'], 'Poland': ['London', 'Poznan']}
```
✅ 
```
cities = {country: [] for country in ["UK", "Poland"]}
cities["UK"].append("London")
cities["Poland"].append("Poznan")
print(cities)  # {'UK': ['London'], 'Poland': ['Poznan']}
```

### needless-else (RUF047)
Avoid `else` clauses that only contains `pass` and `...` statements.
❌ 
```
if foo:
    bar()
else:
    pass
```
✅ 
```
if foo:
    bar()
```

### never-union (RUF020)
Avoid uses of `typing.NoReturn` and `typing.Never` in union types.
❌ 
```
from typing import Never
def func() -> Never | int: ...
```
✅ `def func() -> int: ...`

### non-empty-init-module (RUF067)
Avoid the presence of code in `__init__.py` files.
❌ 
```
"""My module docstring."""
class MyClass:
    def my_method(self): ...
```

### non-octal-permissions (RUF064)
Avoid standard library functions which take a numeric `mode` argument where a non-octal integer literal is passed.
❌ `os.chmod("foo", 644)`
✅ `os.chmod("foo", 0o644)`

### none-not-at-end-of-union (RUF036)
Avoid type annotations where `None` is not at the end of an union.
❌ `def func(arg: None | int): ...`
✅ `def func(arg: int | None): ...`

### os-path-commonprefix (RUF071)
Avoid uses of `os.path.commonprefix`.

### parenthesize-chained-operators (RUF021)
Avoid chained operators where adding parentheses could improve the clarity of the code.

### post-init-default (RUF033)
Avoid `__post_init__` dataclass methods with parameter defaults.
❌ 
```
from dataclasses import InitVar, dataclass
@dataclass
class Foo:
    bar: InitVar[int] = 0
    def __post_init__(self, bar: int = 1, baz: int = 2) -> None:
        print(bar, baz)
…
```
✅ 
```
from dataclasses import InitVar, dataclass
@dataclass
class Foo:
    bar: InitVar[int] = 1
    baz: InitVar[int] = 2
    def __post_init__(self, bar: int, baz: int) -> None:
…
```

### property-without-return (RUF066)
Avoid class `@property` methods that does not have a `return` statement.
❌ 
```
class User:
    @property
    def full_name(self):
        f"{self.first_name} {self.last_name}"
```
✅ 
```
class User:
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
```

### pytest-raises-ambiguous-pattern (RUF043)
Avoid non-raw literal string arguments passed to the `match` parameter of `pytest.raises()` where the string contains at least one unescaped regex metacharacter.
❌ 
```
import pytest
with pytest.raises(Exception, match="A full sentence."):
    do_thing_that_raises()
```

### quadratic-list-summation (RUF017)
Avoid the use of `sum()` to flatten lists of lists, which has quadratic complexity.
❌ 
```
lists = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
joined = sum(lists, [])
```
✅ 
```
lists = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
joined = [*sublist for sublist in lists]
```

### redirected-noqa (RUF101)
Avoid `noqa` directives that use redirected rule codes.
❌ `x = eval(command)  # noqa: PGH001`
✅ `x = eval(command)  # noqa: S307`

### redundant-bool-literal (RUF038)
Avoid `Literal[True, False]` type annotations.
❌ 
```
from typing import Literal
x: Literal[True, False]
y: Literal[True, False, "hello", "world"]
```
✅ 
```
from typing import Literal
x: bool
y: Literal["hello", "world"] | bool
```

### ruff-static-key-dict-comprehension (RUF011)
Avoid dictionary comprehensions that use a static key, like a string literal or a variable defined outside the comprehension.
❌ 
```
data = ["some", "Data"]
{"key": value.upper() for value in data}
```
✅ 
```
data = ["some", "Data"]
{value: value.upper() for value in data}
```

### ruff-unsafe-markup-use (RUF035)
Avoid non-literal strings being passed to `markupsafe.Markup`.
❌ 
```
from markupsafe import Markup
content = "<script>alert('Hello, world!')</script>"
html = Markup(f"<b>{content}</b>")  # XSS
```
✅ 
```
from markupsafe import Markup
content = "<script>alert('Hello, world!')</script>"
html = Markup("<b>{}</b>").format(content)  # Safe
```

### starmap-zip (RUF058)
Avoid `itertools.starmap` calls where the second argument is a `zip` call.
❌ 
```
from itertools import starmap
starmap(func, zip(a, b))
starmap(func, zip(a, b, strict=True))
```
✅ 
```
map(func, a, b)
map(func, a, b, strict=True)  # 3.14+
```

### unmatched-suppression-comment (RUF104)
Avoid unmatched range suppression comments
❌ 
```
def foo():
    # ruff: disable[E501]  # unmatched
    REALLY_LONG_VALUES = [...]
    print(REALLY_LONG_VALUES)
```
✅ 
```
def foo():
    # ruff: disable[E501]
    REALLY_LONG_VALUES = [...]
    # ruff: enable[E501]
    print(REALLY_LONG_VALUES)
```

### unnecessary-assign-before-yield (RUF070)
Avoid variable assignments that immediately precede a `yield` (or `yield from`) of the assigned variable, where the variable is not referenced anywhere else.
❌ 
```
def gen():
    x = 1
    yield x
```
✅ 
```
def gen():
    yield 1
```

### unnecessary-cast-to-int (RUF046)
Avoid `int` conversions of values that are already integers.
❌ 
```
int(len([]))
int(round(foo, None))
```
✅ 
```
len([])
round(foo)
```

### unnecessary-empty-iterable-within-deque-call (RUF037)
Avoid use of `collections.deque` with an empty iterable as the first argument.
❌ 
```
from collections import deque
queue = deque(set())
queue = deque([], 10)
```
✅ 
```
from collections import deque
queue = deque()
queue = deque(maxlen=10)
```

### unnecessary-if (RUF050)
Avoid `if` statements (without `elif` or `else` branches) where the body contains only `pass` or `...`
❌ 
```
import sys
if sys.version_info >= (3, 11):
    pass
```
✅ `import sys`

### unnecessary-iterable-allocation-for-first-element (RUF015)
The following constructs, all of which can be replaced by `next(iter(...))`: - `list(...)[0]` - `tuple(...)[0]` - `list(i for i in ...)[0]` - `[i for i in ...][0]` - `list(...).pop(0)`
❌ 
```
head = list(x)[0]
head = [x * x for x in range(10)][0]
```
✅ 
```
head = next(iter(x))
head = next(x * x for x in range(10))
```

### unnecessary-key-check (RUF019)
Avoid unnecessary key checks prior to accessing a dictionary.
❌ 
```
if "key" in dct and dct["key"]:
    ...
```
✅ 
```
if dct.get("key"):
    ...
```

### unnecessary-nested-literal (RUF041)
Avoid unnecessary nested `Literal`.
❌ 
```
AllModes = Literal[
    Literal["r", "r+"],
    Literal["w", "w+", "wt", "w+t"],
    Literal["r+", "r+t"],
    Literal["a", "a+", "at", "a+t"],
]
```
✅ 
```
AllModes = Literal[
    "r", "r+", "w", "w+", "wt", "w+t", "r+", "r+t", "a", "a+", "at", "a+t"
]
```

### unnecessary-regular-expression (RUF055)
Avoid uses of the `re` module that can be replaced with builtin `str` methods.
❌ `re.sub("abc", "", s)`
✅ `s.replace("abc", "")`

### unnecessary-round (RUF057)
Avoid `round()` calls that have no effect on the input.
❌ `a = round(1, 0)`
✅ `a = 1`

### unraw-re-pattern (RUF039)
Avoid the following `re` and `regex` calls when their first arguments are not raw strings: - For `regex` and `re`: `compile`, `findall`, `finditer`, `fullmatch`, `match`, `search`, `split`, `sub`, `subn`.
❌ `re.compile("foo\\bar")`
✅ `re.compile(r"foo\bar")`

### unsorted-dunder-all (RUF022)
Avoid `__all__` definitions that are not ordered according to an "isort-style" sort.
❌ 
```
import sys
__all__ = [
    "b",
    "c",
    "a",
]
…
```
✅ 
```
import sys
__all__ = [
    "a",
    "b",
    "c",
]
…
```

### unsorted-dunder-slots (RUF023)
Avoid `__slots__` definitions that are not ordered according to a natural sort.
❌ 
```
class Dog:
    __slots__ = "name", "breed"
```
✅ 
```
class Dog:
    __slots__ = "breed", "name"
```

### unused-async (RUF029)
Avoid functions declared `async` that do not await or otherwise use features requiring the function to be declared `async`.
❌ 
```
async def foo():
    bar()
```
✅ 
```
def foo():
    bar()
```

### unused-noqa (RUF100)
Avoid `noqa` directives that are no longer applicable.
❌ 
```
import foo  # noqa: F401
def bar():
    foo.bar()
```
✅ 
```
import foo
def bar():
    foo.bar()
```

### unused-unpacked-variable (RUF059)
Avoid the presence of unused variables in unpacked assignments.
❌ 
```
def get_pair():
    return 1, 2
def foo():
    x, y = get_pair()
    return x
```
✅ 
```
def foo():
    x, _ = get_pair()
    return x
```

### used-dummy-variable (RUF052)
Avoid "dummy variables" (variables that are named as if to indicate they are unused) that are in fact used.
❌ 
```
def function():
    _variable = 3
    # important: avoid shadowing the builtin `id()` function!
    _id = 4
    return _variable + _id
```
✅ 
```
def function():
    variable = 3
    # important: avoid shadowing the builtin `id()` function!
    id_ = 4
    return variable + id_
```

### useless-finally (RUF072)
Avoid `finally` clauses that only contain `pass` or `...` statements
❌ 
```
try:
    foo()
except Exception:
    bar()
finally:
    pass
```
✅ 
```
try:
    foo()
except Exception:
    bar()
```

### useless-if-else (RUF034)
Avoid useless `if`-`else` conditions with identical arms.
❌ `foo = x if y else x`
✅ `foo = x`

### zip-instead-of-pairwise (RUF007)
Avoid use of `zip()` to iterate over successive pairs of elements.
❌ 
```
letters = "ABCD"
zip(letters, letters[1:])  # ("A", "B"), ("B", "C"), ("C", "D")
```
✅ 
```
from itertools import pairwise
letters = "ABCD"
pairwise(letters)  # ("A", "B"), ("B", "C"), ("C", "D")
```

### Plugin: `tryceratops`

### error-instead-of-exception (TRY400)
Avoid uses of `logging.error` instead of `logging.exception` when logging an exception.
❌ 
```
import logging
def func():
    try:
        raise NotImplementedError
    except NotImplementedError:
        logging.error("Exception occurred")
```
✅ 
```
import logging
def func():
    try:
        raise NotImplementedError
    except NotImplementedError:
        logging.exception("Exception occurred")
```

### raise-vanilla-args (TRY003)
Avoid long exception messages that are not defined in the exception class itself.
❌ 
```
class CantBeNegative(Exception):
    pass
def foo(x):
    if x < 0:
        raise CantBeNegative(f"{x} is negative")
```
✅ 
```
class CantBeNegative(Exception):
    def __init__(self, number):
        super().__init__(f"{number} is negative")
def foo(x):
    if x < 0:
        raise CantBeNegative(x)
```

### raise-vanilla-class (TRY002)
Avoid code that raises `Exception` or `BaseException` directly.
❌ 
```
def main_function():
    if not cond:
        raise Exception()
def consumer_func():
    try:
        do_step()
…
```
✅ 
```
def main_function():
    if not cond:
        raise CustomException()
def consumer_func():
    try:
        do_step()
…
```

### raise-within-try (TRY301)
Avoid `raise` statements within `try` blocks.
❌ 
```
def bar():
    pass
def foo():
    try:
        a = bar()
        if not a:
…
```
✅ 
```
def bar():
    raise ValueError
def foo():
    try:
        a = bar()  # refactored `bar` to raise `ValueError`
    except ValueError:
…
```

### reraise-no-cause (TRY200)
Avoid exceptions that are re-raised without specifying the cause via the `from` keyword.
❌ 
```
def reciprocal(n):
    try:
        return 1 / n
    except ZeroDivisionError:
        raise ValueError()
```
✅ 
```
def reciprocal(n):
    try:
        return 1 / n
    except ZeroDivisionError as exc:
        raise ValueError() from exc
```

### try-consider-else (TRY300)
Avoid `return` statements in `try` blocks.
❌ 
```
import logging
def reciprocal(n):
    try:
        rec = 1 / n
        print(f"reciprocal of {n} is {rec}")
        return rec
…
```
✅ 
```
import logging
def reciprocal(n):
    try:
        rec = 1 / n
    except ZeroDivisionError:
        logging.exception("Exception occurred")
…
```

### type-check-without-type-error (TRY004)
Avoid type checks that do not raise `TypeError`.
❌ 
```
def foo(n: int):
    if isinstance(n, int):
        pass
    else:
        raise ValueError("n must be an integer")
```
✅ 
```
def foo(n: int):
    if isinstance(n, int):
        pass
    else:
        raise TypeError("n must be an integer")
```

### useless-try-except (TRY203)
Avoid immediate uses of `raise` within exception handlers.
❌ 
```
def foo():
    try:
        bar()
    except NotImplementedError:
        raise
```
✅ 
```
def foo():
    bar()
```

### verbose-log-message (TRY401)
Avoid excessive logging of exception objects.
❌ 
```
try:
    ...
except ValueError as e:
    logger.exception(f"Found an error: {e}")
```
✅ 
```
try:
    ...
except ValueError:
    logger.exception("Found an error")
```

### verbose-raise (TRY201)
Avoid needless exception names in `raise` statements.
❌ 
```
def foo():
    try:
        ...
    except ValueError as exc:
        raise exc
```
✅ 
```
def foo():
    try:
        ...
    except ValueError:
        raise
```


## Tier 2 — Modernization & Performance
*188 rules*

### Plugin: `Perflint`

### incorrect-dict-iterator (PERF102)
Avoid uses of `dict.items()` that discard either the key or the value when iterating over the dictionary.
❌ 
```
obj = {"a": 1, "b": 2}
for key, value in obj.items():
    print(value)
```
✅ 
```
obj = {"a": 1, "b": 2}
for value in obj.values():
    print(value)
```

### manual-dict-comprehension (PERF403)
Avoid `for` loops that can be replaced by a dictionary comprehension.
❌ 
```
pairs = (("a", 1), ("b", 2))
result = {}
for x, y in pairs:
    if y % 2:
        result[x] = y
```
✅ 
```
pairs = (("a", 1), ("b", 2))
result = {x: y for x, y in pairs if y % 2}
```

### manual-list-comprehension (PERF401)
Avoid `for` loops that can be replaced by a list comprehension.
❌ 
```
original = list(range(10000))
filtered = []
for i in original:
    if i % 2:
        filtered.append(i)
```
✅ 
```
original = list(range(10000))
filtered = [x for x in original if x % 2]
```

### manual-list-copy (PERF402)
Avoid `for` loops that can be replaced by a making a copy of a list.
❌ 
```
original = list(range(10000))
filtered = []
for i in original:
    filtered.append(i)
```
✅ 
```
original = list(range(10000))
filtered = list(original)
```

### try-except-in-loop (PERF203)
Avoid uses of except handling via `try`-`except` within `for` and `while` loops.

### unnecessary-list-cast (PERF101)
Avoid explicit casts to `list` on for-loop iterables.
❌ 
```
items = (1, 2, 3)
for i in list(items):
    print(i)
```
✅ 
```
items = (1, 2, 3)
for i in items:
    print(i)
```

### Plugin: `flake8-2020`

### six-py3 (YTT202)
Avoid uses of `six.PY3`.
❌ 
```
import six
six.PY3  # `False` on Python 4.
```
✅ 
```
import six
not six.PY2  # `True` on Python 4.
```

### sys-version-cmp-str10 (YTT302)
Avoid comparisons that test `sys.version` against string literals, such that the comparison would fail if the major version number were ever incremented to Python 10 or higher.
❌ 
```
import sys
sys.version >= "3"  # `False` on Python 10.
```
✅ 
```
import sys
sys.version_info >= (3,)  # `True` on Python 10.
```

### sys-version-cmp-str3 (YTT103)
Avoid comparisons that test `sys.version` against string literals, such that the comparison will evaluate to `False` on Python 3.10 or later.
❌ 
```
import sys
sys.version > "3.9"  # `False` on Python 3.10.
```
✅ 
```
import sys
sys.version_info > (3, 9)  # `True` on Python 3.10.
```

### sys-version-info-minor-cmp-int (YTT204)
Avoid comparisons that test `sys.version_info.minor` against an integer.
❌ 
```
import sys
if sys.version_info.minor < 7:
    print("Python 3.6 or earlier.")  # This will be printed on Python 4.0.
```
✅ 
```
import sys
if sys.version_info < (3, 7):
    print("Python 3.6 or earlier.")
```

### sys-version-info0-eq3 (YTT201)
Avoid equality comparisons against the major version returned by `sys.version_info` (e.g., `sys.version_info[0] == 3` or `sys.version_info[0] != 3`).
❌ 
```
import sys
if sys.version_info[0] == 3:
    ...
else:
    print("Python 2")  # This will be printed on Python 4.
```
✅ 
```
import sys
if sys.version_info >= (3,):
    ...
else:
    print("Python 2")  # This will not be printed on Python 4.
```

### sys-version-info1-cmp-int (YTT203)
Avoid comparisons that test `sys.version_info[1]` against an integer.
❌ 
```
import sys
if sys.version_info[1] < 7:
    print("Python 3.6 or earlier.")  # This will be printed on Python 4.0.
```
✅ 
```
import sys
if sys.version_info < (3, 7):
    print("Python 3.6 or earlier.")
```

### sys-version-slice1 (YTT303)
Avoid uses of `sys.version[:1]`.
❌ 
```
import sys
sys.version[:1]  # If using Python 10, this evaluates to "1".
```
✅ 
```
import sys
f"{sys.version_info.major}"  # If using Python 10, this evaluates to "10".
```

### sys-version-slice3 (YTT101)
Avoid uses of `sys.version[:3]`.
❌ 
```
import sys
sys.version[:3]  # Evaluates to "3.1" on Python 3.10.
```
✅ 
```
import sys
sys.version_info[:2]  # Evaluates to (3, 10) on Python 3.10.
```

### sys-version0 (YTT301)
Avoid uses of `sys.version[0]`.
❌ 
```
import sys
sys.version[0]  # If using Python 10, this evaluates to "1".
```
✅ 
```
import sys
f"{sys.version_info.major}"  # If using Python 10, this evaluates to "10".
```

### sys-version2 (YTT102)
Avoid uses of `sys.version[2]`.
❌ 
```
import sys
sys.version[2]  # Evaluates to "1" on Python 3.10.
```
✅ 
```
import sys
f"{sys.version_info.minor}"  # Evaluates to "10" on Python 3.10.
```

### Plugin: `flake8-comprehensions`

### unnecessary-call-around-sorted (C413)
Avoid unnecessary `list()` or `reversed()` calls around `sorted()` calls.
❌ `reversed(sorted(iterable))`
✅ `sorted(iterable, reverse=True)`

### unnecessary-collection-call (C408)
Avoid unnecessary `dict()`, `list()` or `tuple()` calls that can be rewritten as empty literals.
❌ 
```
dict()
dict(a=1, b=2)
list()
tuple()
```
✅ 
```
{}
{"a": 1, "b": 2}
[]
()
```

### unnecessary-comprehension (C416)
Avoid unnecessary dict, list, and set comprehension.
❌ 
```
{a: b for a, b in iterable}
[x for x in iterable]
{x for x in iterable}
```
✅ 
```
dict(iterable)
list(iterable)
set(iterable)
```

### unnecessary-comprehension-in-call (C419)
Avoid unnecessary list or set comprehensions passed to builtin functions that take an iterable.
❌ 
```
any([x.id for x in bar])
all([x.id for x in bar])
sum([x.val for x in bar])
min([x.val for x in bar])
max([x.val for x in bar])
```
✅ 
```
any(x.id for x in bar)
all(x.id for x in bar)
sum(x.val for x in bar)
min(x.val for x in bar)
max(x.val for x in bar)
```

### unnecessary-dict-comprehension-for-iterable (C420)
Avoid unnecessary dict comprehension when creating a dictionary from an iterable.
❌ 
```
{a: None for a in iterable}
{a: 1 for a in iterable}
```
✅ 
```
dict.fromkeys(iterable)
dict.fromkeys(iterable, 1)
```

### unnecessary-double-cast-or-process (C414)
Avoid unnecessary `list()`, `reversed()`, `set()`, `sorted()`, and `tuple()` call within `list()`, `set()`, `sorted()`, and `tuple()` calls.
❌ `list(tuple(iterable))`
✅ `list(iterable)`

### unnecessary-generator-dict (C402)
Avoid unnecessary generators that can be rewritten as dict comprehensions.
❌ `dict((x, f(x)) for x in foo)`
✅ `{x: f(x) for x in foo}`

### unnecessary-generator-list (C400)
Avoid unnecessary generators that can be rewritten as list comprehensions (or with `list()` directly).
❌ 
```
list(f(x) for x in foo)
list(x for x in foo)
list((x for x in foo))
```
✅ 
```
[f(x) for x in foo]
list(foo)
list(foo)
```

### unnecessary-generator-set (C401)
Avoid unnecessary generators that can be rewritten as set comprehensions (or with `set()` directly).
❌ 
```
set(f(x) for x in foo)
set(x for x in foo)
set((x for x in foo))
```
✅ 
```
{f(x) for x in foo}
set(foo)
set(foo)
```

### unnecessary-list-call (C411)
Avoid unnecessary `list()` calls around list comprehensions.
❌ `list([f(x) for x in foo])`

### unnecessary-list-comprehension-dict (C404)
Avoid unnecessary list comprehensions.
❌ `dict([(x, f(x)) for x in foo])`
✅ `{x: f(x) for x in foo}`

### unnecessary-list-comprehension-set (C403)
Avoid unnecessary list comprehensions.
❌ `set([f(x) for x in foo])`
✅ `{f(x) for x in foo}`

### unnecessary-literal-dict (C406)
Avoid unnecessary list or tuple literals.
❌ 
```
dict([(1, 2), (3, 4)])
dict(((1, 2), (3, 4)))
dict([])
```
✅ 
```
{1: 2, 3: 4}
{1: 2, 3: 4}
{}
```

### unnecessary-literal-set (C405)
Avoid `set()` calls that take unnecessary list or tuple literals as arguments.
❌ 
```
set([1, 2])
set((1, 2))
set([])
```
✅ 
```
{1, 2}
{1, 2}
set()
```

### unnecessary-literal-within-dict-call (C418)
Avoid `dict()` calls that take unnecessary dict literals or dict comprehensions as arguments.
❌ 
```
dict({})
dict({"a": 1})
```
✅ 
```
{}
{"a": 1}
```

### unnecessary-literal-within-list-call (C410)
Avoid `list()` calls that take unnecessary list or tuple literals as arguments.
❌ 
```
list([1, 2])
list((1, 2))
```
✅ 
```
[1, 2]
[1, 2]
```

### unnecessary-literal-within-tuple-call (C409)
Avoid `tuple` calls that take unnecessary list or tuple literals as arguments.
❌ 
```
tuple([1, 2])
tuple((1, 2))
tuple([x for x in range(10)])
```
✅ 
```
(1, 2)
(1, 2)
tuple(x for x in range(10))
```

### unnecessary-map (C417)
Avoid unnecessary `map()` calls with lambda functions.
❌ `map(lambda x: x + 1, iterable)`
✅ `(x + 1 for x in iterable)`

### unnecessary-subscript-reversal (C415)
Avoid unnecessary subscript reversal of iterable.
❌ 
```
sorted(iterable[::-1])
set(iterable[::-1])
reversed(iterable[::-1])
```
✅ 
```
sorted(iterable)
set(iterable)
iterable
```

### Plugin: `flake8-future-annotations`

### future-required-type-annotation (FA102)
Avoid uses of PEP 585- and PEP 604-style type annotations in Python modules that lack the required `from __future__ import annotations` import for compatibility with older Python versions.
❌ `def func(obj: dict[str, int | None]) -> None: ...`
✅ 
```
from __future__ import annotations
def func(obj: dict[str, int | None]) -> None: ...
```

### future-rewritable-type-annotation (FA100)
Avoid missing `from __future__ import annotations` imports upon detecting type annotations that can be written more succinctly under PEP 563.
❌ 
```
from typing import List, Dict, Optional
def func(obj: Dict[str, Optional[int]]) -> None: ...
```
✅ 
```
from __future__ import annotations
from typing import List, Dict, Optional
def func(obj: Dict[str, Optional[int]]) -> None: ...
```

### Plugin: `flake8-pyi`

### any-eq-ne-annotation (PYI032)
Avoid `__eq__` and `__ne__` implementations that use `typing.Any` as the type annotation for their second parameter.
❌ 
```
from typing import Any
class Foo:
    def __eq__(self, obj: Any) -> bool: ...
```
✅ 
```
class Foo:
    def __eq__(self, obj: object) -> bool: ...
```

### argument-default-in-stub (PYI014)
Avoid untyped function arguments in stubs with default values that are not "simple" /// (i.e., `int`, `float`, `complex`, `bytes`, `str`, `bool`, `None`, `...`, or simple container literals).
❌ `def foo(arg=bar()) -> None: ...`
✅ `def foo(arg=...) -> None: ...`

### assignment-default-in-stub (PYI015)
Avoid assignments in stubs with default values that are not "simple" (i.e., `int`, `float`, `complex`, `bytes`, `str`, `bool`, `None`, `...`, or simple container literals).
❌ `foo: str = bar()`
✅ `foo: str = ...`

### bad-exit-annotation (PYI036)
Avoid incorrect function signatures on `__exit__` and `__aexit__` methods.
❌ 
```
from types import TracebackType
class Foo:
    def __exit__(
        self, typ: BaseException, exc: BaseException, tb: TracebackType
    ) -> None: ...
```
✅ 
```
from types import TracebackType
class Foo:
    def __exit__(
        self,
        typ: type[BaseException] | None,
        exc: BaseException | None,
…
```

### bad-version-info-comparison (PYI006)
Avoid uses of comparators other than `<` and `>=` for `sys.version_info` checks.
❌ 
```
import sys
if sys.version_info > (3, 8): ...
```
✅ 
```
import sys
if sys.version_info >= (3, 9): ...
```

### bad-version-info-order (PYI066)
Avoid code that branches on `sys.version_info` comparisons where branches corresponding to older Python versions come before branches corresponding to newer Python versions.
❌ 
```
import sys
if sys.version_info < (3, 10):
    def read_data(x, *, preserve_order=True): ...
else:
    def read_data(x): ...
```
✅ 
```
if sys.version_info >= (3, 10):
    def read_data(x): ...
else:
    def read_data(x, *, preserve_order=True): ...
```

### byte-string-usage (PYI057)
Avoid uses of `typing.ByteString` or `collections.abc.ByteString`.
❌ `from typing import ByteString`
✅ `from collections.abc import Buffer`

### collections-named-tuple (PYI024)
Avoid uses of `collections.namedtuple` in stub files.
❌ 
```
from collections import namedtuple
Person = namedtuple("Person", ["name", "age"])
```
✅ 
```
from typing import NamedTuple
class Person(NamedTuple):
    name: str
    age: int
```

### complex-assignment-in-stub (PYI017)
Avoid assignments with multiple or non-name targets in stub files.
❌ 
```
from typing import TypeAlias
a = b = int
class Klass: ...
Klass.X: TypeAlias = int
```
✅ 
```
from typing import TypeAlias
a: TypeAlias = int
b: TypeAlias = int
class Klass:
    X: TypeAlias = int
```

### complex-if-statement-in-stub (PYI002)
Avoid `if` statements with complex conditionals in stubs.
❌ 
```
import sys
if (3, 10) <= sys.version_info < (3, 12): ...
```
✅ 
```
import sys
if sys.version_info >= (3, 10) and sys.version_info < (3, 12): ...
```

### custom-type-var-for-self (PYI019)
Avoid methods that use custom `TypeVar`s in their annotations when they could use `Self` instead.
❌ 
```
from typing import TypeVar
_S = TypeVar("_S", bound="Foo")
class Foo:
    def __new__(cls: type[_S], *args: str, **kwargs: int) -> _S: ...
    def foo(self: _S, arg: bytes) -> _S: ...
    @classmethod
…
```
✅ 
```
from typing import Self
class Foo:
    def __new__(cls, *args: str, **kwargs: int) -> Self: ...
    def foo(self, arg: bytes) -> Self: ...
    @classmethod
    def bar(cls, arg: int) -> Self: ...
```

### docstring-in-stub (PYI021)
Avoid the presence of docstrings in stub files.
❌ 
```
def func(param: int) -> str:
    """This is a docstring."""
    ...
```
✅ `def func(param: int) -> str: ...`

### duplicate-literal-member (PYI062)
Avoid duplicate members in a `typing.Literal[]` slice.
❌ 
```
from typing import Literal
foo: Literal["a", "b", "a"]
```
✅ 
```
from typing import Literal
foo: Literal["a", "b"]
```

### duplicate-union-member (PYI016)
Avoid duplicate union members.
❌ `foo: str | str`
✅ `foo: str`

### ellipsis-in-non-empty-class-body (PYI013)
Removes ellipses (`...`) in otherwise non-empty class bodies.
❌ 
```
class Foo:
    ...
    value: int
```
✅ 
```
class Foo:
    value: int
```

### future-annotations-in-stub (PYI044)
Avoid the presence of the `from __future__ import annotations` import statement in stub files.

### generator-return-from-iter-method (PYI058)
Avoid simple `__iter__` methods that return `Generator`, and for simple `__aiter__` methods that return `AsyncGenerator`.

### generic-not-last-base-class (PYI059)
Avoid classes inheriting from `typing.Generic[]` where `Generic[]` is not the last base class in the bases tuple.

### iter-method-return-iterable (PYI045)
Avoid `__iter__` methods in stubs that return `Iterable[T]` instead of an `Iterator[T]`.
❌ 
```
import collections.abc
class Klass:
    def __iter__(self) -> collections.abc.Iterable[str]: ...
```
✅ 
```
import collections.abc
class Klass:
    def __iter__(self) -> collections.abc.Iterator[str]: ...
```

### no-return-argument-annotation-in-stub (PYI050)
Avoid uses of `typing.NoReturn` (and `typing_extensions.NoReturn`) for parameter annotations.
❌ 
```
from typing import NoReturn
def foo(x: NoReturn): ...
```
✅ 
```
from typing import Never
def foo(x: Never): ...
```

### non-empty-stub-body (PYI010)
Avoid non-empty function stub bodies.
❌ 
```
def double(x: int) -> int:
    return x * 2
```
✅ `def double(x: int) -> int: ...`

### non-self-return-type (PYI034)
Avoid methods that are annotated with a fixed return type which should instead be returning `Self`.
❌ 
```
class Foo:
    def __new__(cls, *args: Any, **kwargs: Any) -> Foo: ...
    def __enter__(self) -> Foo: ...
    async def __aenter__(self) -> Foo: ...
    def __iadd__(self, other: Foo) -> Foo: ...
```
✅ 
```
from typing_extensions import Self
class Foo:
    def __new__(cls, *args: Any, **kwargs: Any) -> Self: ...
    def __enter__(self) -> Self: ...
    async def __aenter__(self) -> Self: ...
    def __iadd__(self, other: Foo) -> Self: ...
```

### numeric-literal-too-long (PYI054)
Avoid numeric literals with a string representation longer than ten characters.
❌ `def foo(arg: int = 693568516352839939918568862861217771399698285293568) -> None: ...`
✅ `def foo(arg: int = ...) -> None: ...`

### pass-in-class-body (PYI012)
Avoid the presence of the `pass` statement in non-empty class bodies in `.pyi` files.
❌ 
```
class MyClass:
    x: int
    pass
```
✅ 
```
class MyClass:
    x: int
```

### pass-statement-stub-body (PYI009)
Avoid `pass` statements in empty stub bodies.
❌ `def foo(bar: int) -> list[int]: pass`
✅ `def foo(bar: int) -> list[int]: ...`

### patch-version-comparison (PYI004)
Avoid Python version comparisons in stubs that compare against patch versions (e.g., Python 3.8.3) instead of major and minor versions (e.g., Python 3.8).
❌ 
```
import sys
if sys.version_info >= (3, 4, 3): ...
```
✅ 
```
import sys
if sys.version_info >= (3, 4): ...
```

### pep484-style-positional-only-parameter (PYI063)
Avoid the presence of PEP 484-style positional-only parameters.
❌ `def foo(__x: int) -> None: ...`
✅ `def foo(x: int, /) -> None: ...`

### quoted-annotation-in-stub (PYI020)
Avoid quoted type annotations in stub (`.pyi`) files, which should be avoided.
❌ `def function() -> "int": ...`
✅ `def function() -> int: ...`

### redundant-final-literal (PYI064)
Avoid redundant `Final[Literal[...]]` annotations.
❌ 
```
from typing import Final, Literal
x: Final[Literal[42]]
y: Final[Literal[42]] = 42
```
✅ 
```
from typing import Final, Literal
x: Final = 42
y: Final = 42
```

### redundant-literal-union (PYI051)
Avoid redundant unions between a `Literal` and a builtin supertype of that `Literal`.
❌ 
```
from typing import Literal
x: Literal["A", b"B"] | str
```
✅ 
```
from typing import Literal
x: Literal[b"B"] | str
```

### redundant-none-literal (PYI061)
Avoid redundant `Literal[None]` annotations.
❌ 
```
from typing import Literal
Literal[None]
Literal[1, 2, 3, "foo", 5, None]
```
✅ 
```
from typing import Literal
None
Literal[1, 2, 3, "foo", 5] | None
```

### redundant-numeric-union (PYI041)
Avoid parameter annotations that contain redundant unions between builtin numeric types (e.g., `int | float`).
❌ `def foo(x: float | int | str) -> None: ...`
✅ `def foo(x: float | str) -> None: ...`

### snake-case-type-alias (PYI042)
Avoid type aliases that do not use the CamelCase naming convention.
❌ 
```
from typing import TypeAlias
type_alias_name: TypeAlias = int
```
✅ 
```
from typing import TypeAlias
TypeAliasName: TypeAlias = int
```

### str-or-repr-defined-in-stub (PYI029)
Avoid redundant definitions of `__str__` or `__repr__` in stubs.
❌ 
```
class Foo:
    def __repr__(self) -> str: ...
```

### string-or-bytes-too-long (PYI053)
Avoid the use of string and bytes literals longer than 50 characters in stub (`.pyi`) files.
❌ `def foo(arg: str = "51 character stringgggggggggggggggggggggggggggggggg") -> None: ...`
✅ `def foo(arg: str = ...) -> None: ...`

### stub-body-multiple-statements (PYI048)
Avoid functions in stub (`.pyi`) files that contain multiple statements.
❌ 
```
def function():
    x = 1
    y = 2
    return x + y
```
✅ `def function(): ...`

### t-suffixed-type-alias (PYI043)
Avoid private type alias definitions suffixed with 'T'.
❌ 
```
from typing import TypeAlias
_MyTypeT: TypeAlias = int
```
✅ 
```
from typing import TypeAlias
_MyType: TypeAlias = int
```

### type-alias-without-annotation (PYI026)
Avoid type alias definitions that are not annotated with `typing.TypeAlias`.
❌ `Vector = list[float]`
✅ 
```
from typing import TypeAlias
Vector: TypeAlias = list[float]
```

### type-comment-in-stub (PYI033)
Avoid the use of type comments (e.g., `x = 1 # type: int`) in stub files.
❌ `x = 1  # type: int`
✅ `x: int = 1`

### typed-argument-default-in-stub (PYI011)
Avoid typed function arguments in stubs with complex default values.
❌ `def foo(arg: list[int] = list(range(10_000))) -> None: ...`
✅ `def foo(arg: list[int] = ...) -> None: ...`

### unaliased-collections-abc-set-import (PYI025)
Avoid `from collections.abc import Set` imports that do not alias `Set` to `AbstractSet`.
❌ `from collections.abc import Set`
✅ `from collections.abc import Set as AbstractSet`

### unannotated-assignment-in-stub (PYI052)
Avoid unannotated assignments in stub (`.pyi`) files.

### unassigned-special-variable-in-stub (PYI035)
Ensure `__all__`, `__match_args__`, and `__slots__` variables are assigned to values when defined in stub files.
❌ `__all__: list[str]`
✅ `__all__: list[str] = ["foo", "bar"]`

### unnecessary-literal-union (PYI030)
Avoid the presence of multiple literal types in a union.
❌ 
```
from typing import Literal
field: Literal[1] | Literal[2] | str
```
✅ 
```
from typing import Literal
field: Literal[1, 2] | str
```

### unnecessary-type-union (PYI055)
Avoid the presence of multiple `type`s in a union.
❌ `field: type[int] | type[float] | str`
✅ `field: type[int | float] | str`

### unprefixed-type-param (PYI001)
Ensure type `TypeVar`s, `ParamSpec`s, and `TypeVarTuple`s in stubs have names prefixed with `_`.
❌ 
```
from typing import TypeVar
T = TypeVar("T")
```
✅ 
```
from typing import TypeVar
_T = TypeVar("_T")
```

### unrecognized-platform-check (PYI007)
Avoid unrecognized `sys.platform` checks.
❌ 
```
import sys
if sys.platform == "xunil"[::-1]:
    # Linux specific definitions
    ...
else:
    # Posix specific definitions
…
```

### unrecognized-platform-name (PYI008)
Avoid unrecognized platform names in `sys.platform` checks.
❌ 
```
import sys
if sys.platform == "linus": ...
```
✅ 
```
import sys
if sys.platform == "linux": ...
```

### unrecognized-version-info-check (PYI003)
Avoid problematic `sys.version_info`-related conditions in stubs.
❌ 
```
import sys
if sys.version_info[0] == "2": ...
```
✅ 
```
import sys
if sys.version_info[0] == 2: ...
```

### unsupported-method-call-on-all (PYI056)
Ensure `append`, `extend` and `remove` methods are not called on `__all__`.
❌ 
```
import sys
__all__ = ["A", "B"]
if sys.version_info >= (3, 10):
    __all__.append("C")
if sys.version_info >= (3, 11):
    __all__.remove("B")
```
✅ 
```
import sys
__all__ = ["A"]
if sys.version_info < (3, 11):
    __all__ += ["B"]
if sys.version_info >= (3, 10):
    __all__ += ["C"]
```

### unused-private-protocol (PYI046)
Avoid the presence of unused private `typing.Protocol` definitions.
❌ 
```
import typing
class _PrivateProtocol(typing.Protocol):
    foo: int
```
✅ 
```
import typing
class _PrivateProtocol(typing.Protocol):
    foo: int
def func(arg: _PrivateProtocol) -> None: ...
```

### unused-private-type-alias (PYI047)
Avoid the presence of unused private type aliases.
❌ 
```
import typing
_UnusedTypeAlias: typing.TypeAlias = int
```
✅ 
```
import typing
_UsedTypeAlias: typing.TypeAlias = int
def func(arg: _UsedTypeAlias) -> _UsedTypeAlias: ...
```

### unused-private-type-var (PYI018)
Avoid the presence of unused private `TypeVar`, `ParamSpec` or `TypeVarTuple` declarations.
❌ 
```
import typing
import typing_extensions
_T = typing.TypeVar("_T")
_Ts = typing_extensions.TypeVarTuple("_Ts")
```

### unused-private-typed-dict (PYI049)
Avoid the presence of unused private `typing.TypedDict` definitions.
❌ 
```
import typing
class _UnusedPrivateTypedDict(typing.TypedDict):
    foo: list[int]
```
✅ 
```
import typing
class _UsedPrivateTypedDict(typing.TypedDict):
    foo: set[str]
def func(arg: _UsedPrivateTypedDict) -> _UsedPrivateTypedDict: ...
```

### wrong-tuple-length-version-comparison (PYI005)
Avoid Python version comparisons that compare against a tuple of the wrong length.
❌ 
```
import sys
if sys.version_info[:2] == (3,): ...
```
✅ 
```
import sys
if sys.version_info[0] == 3: ...
```

### Plugin: `flake8-tidy-imports`

### banned-api (TID251)
Avoid banned imports.

### banned-module-level-imports (TID253)
Avoid module-level imports that should instead be imported lazily (e.g., within a function definition, or an `if TYPE_CHECKING:` block, or some other nested context).
❌ 
```
import tensorflow as tf
def show_version():
    print(tf.__version__)
```
✅ 
```
def show_version():
    import tensorflow as tf
    print(tf.__version__)
```

### lazy-import-mismatch (TID254)
Enforce the configured lazy-import policy in contexts where `lazy import` is legal.
❌ `import typing`
✅ `lazy import typing`

### relative-imports (TID252)
Avoid relative imports.
❌ `from .. import foo`
✅ `from mypkg import foo`

### Plugin: `flake8-type-checking`

### empty-type-checking-block (TC005)
Avoid an empty type-checking block.
❌ 
```
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass
print("Hello, world!")
```
✅ `print("Hello, world!")`

### quoted-type-alias (TC008)
Avoid unnecessary quotes in PEP 613 explicit type aliases and PEP 695 type statements.
❌ 
```
from typing import TypeAlias
OptInt: TypeAlias = "int | None"
```
✅ 
```
from typing import TypeAlias
OptInt: TypeAlias = int | None
```

### runtime-cast-value (TC006)
Avoid unquoted type expressions in `typing.cast()` calls.
❌ 
```
from typing import cast
x = cast(dict[str, int], foo)
```
✅ 
```
from typing import cast
x = cast("dict[str, int]", foo)
```

### runtime-import-in-type-checking-block (TC004)
Avoid imports that are required at runtime but are only defined in type-checking blocks.
❌ 
```
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import foo
def bar() -> None:
    foo.bar()  # raises NameError: name 'foo' is not defined
```
✅ 
```
import foo
def bar() -> None:
    foo.bar()
```

### runtime-string-union (TC010)
Avoid the presence of string literals in `X | Y`-style union types.
❌ 
```
var: "Foo" | None
class Foo: ...
```
✅ 
```
from __future__ import annotations
var: Foo | None
class Foo: ...
```

### typing-only-first-party-import (TC001)
Avoid first-party imports that are only used for type annotations, but aren't defined in a type-checking block.
❌ 
```
from __future__ import annotations
from . import local_module
def func(sized: local_module.Container) -> int:
    return len(sized)
```
✅ 
```
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from . import local_module
def func(sized: local_module.Container) -> int:
    return len(sized)
```

### typing-only-standard-library-import (TC003)
Avoid standard library imports that are only used for type annotations, but aren't defined in a type-checking block.
❌ 
```
from __future__ import annotations
from pathlib import Path
def func(path: Path) -> str:
    return str(path)
```
✅ 
```
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pathlib import Path
def func(path: Path) -> str:
    return str(path)
```

### typing-only-third-party-import (TC002)
Avoid third-party imports that are only used for type annotations, but aren't defined in a type-checking block.
❌ 
```
from __future__ import annotations
import pandas as pd
def func(df: pd.DataFrame) -> int:
    return len(df)
```
✅ 
```
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import pandas as pd
def func(df: pd.DataFrame) -> int:
    return len(df)
```

### unquoted-type-alias (TC007)
If PEP 613 explicit type aliases contain references to symbols that are not available at runtime.
❌ 
```
from typing import TYPE_CHECKING, TypeAlias
if TYPE_CHECKING:
    from foo import Foo
OptFoo: TypeAlias = Foo | None
```
✅ 
```
from typing import TYPE_CHECKING, TypeAlias
if TYPE_CHECKING:
    from foo import Foo
OptFoo: TypeAlias = "Foo | None"
```

### Plugin: `flake8-use-pathlib`

### builtin-open (PTH123)
Avoid uses of the `open()` builtin.
❌ 
```
with open("f1.py", "wb") as fp:
    ...
```
✅ 
```
from pathlib import Path
with Path("f1.py").open("wb") as fp:
    ...
```

### glob (PTH207)
Avoid the use of `glob.glob()` and `glob.iglob()`.
❌ 
```
import glob
import os
glob.glob(os.path.join("my_path", "requirements*.txt"))
```
✅ 
```
from pathlib import Path
Path("my_path").glob("requirements*.txt")
```

### invalid-pathlib-with-suffix (PTH210)
Avoid `pathlib.Path.with_suffix()` calls where the given suffix does not have a leading dot or the given suffix is a single dot `"."` and the Python version is less than 3.14.
❌ 
```
from pathlib import Path
path = Path()
path.with_suffix("py")
```
✅ 
```
from pathlib import Path
path = Path()
path.with_suffix(".py")
```

### os-chmod (PTH101)
Avoid uses of `os.chmod`.
❌ 
```
import os
os.chmod("file.py", 0o444)
```
✅ 
```
from pathlib import Path
Path("file.py").chmod(0o444)
```

### os-getcwd (PTH109)
Avoid uses of `os.getcwd` and `os.getcwdb`.
❌ 
```
import os
cwd = os.getcwd()
```
✅ 
```
from pathlib import Path
cwd = Path.cwd()
```

### os-listdir (PTH208)
Avoid uses of `os.listdir`.
❌ 
```
p = "."
for d in os.listdir(p):
    ...
if os.listdir(p):
    ...
if "file" in os.listdir(p):
…
```
✅ 
```
p = Path(".")
for d in p.iterdir():
    ...
if any(p.iterdir()):
    ...
if (p / "file").exists():
…
```

### os-makedirs (PTH103)
Avoid uses of `os.makedirs`.
❌ 
```
import os
os.makedirs("./nested/directory/")
```
✅ 
```
from pathlib import Path
Path("./nested/directory/").mkdir(parents=True)
```

### os-mkdir (PTH102)
Avoid uses of `os.mkdir`.
❌ 
```
import os
os.mkdir("./directory/")
```
✅ 
```
from pathlib import Path
Path("./directory/").mkdir()
```

### os-path-abspath (PTH100)
Avoid uses of `os.path.abspath`.
❌ 
```
import os
file_path = os.path.abspath("../path/to/file")
```
✅ 
```
from pathlib import Path
file_path = Path("../path/to/file").resolve()
```

### os-path-basename (PTH119)
Avoid uses of `os.path.basename`.
❌ 
```
import os
os.path.basename(__file__)
```
✅ 
```
from pathlib import Path
Path(__file__).name
```

### os-path-dirname (PTH120)
Avoid uses of `os.path.dirname`.
❌ 
```
import os
os.path.dirname(__file__)
```
✅ 
```
from pathlib import Path
Path(__file__).parent
```

### os-path-exists (PTH110)
Avoid uses of `os.path.exists`.
❌ 
```
import os
os.path.exists("file.py")
```
✅ 
```
from pathlib import Path
Path("file.py").exists()
```

### os-path-expanduser (PTH111)
Avoid uses of `os.path.expanduser`.
❌ 
```
import os
os.path.expanduser("~/films/Monty Python")
```
✅ 
```
from pathlib import Path
Path("~/films/Monty Python").expanduser()
```

### os-path-getatime (PTH203)
Avoid uses of `os.path.getatime`.
❌ 
```
import os
os.path.getatime(__file__)
```
✅ 
```
from pathlib import Path
Path(__file__).stat().st_atime
```

### os-path-getctime (PTH205)
Avoid uses of `os.path.getctime`.
❌ 
```
import os
os.path.getctime(__file__)
```
✅ 
```
from pathlib import Path
Path(__file__).stat().st_ctime
```

### os-path-getmtime (PTH204)
Avoid uses of `os.path.getmtime`.
❌ 
```
import os
os.path.getmtime(__file__)
```
✅ 
```
from pathlib import Path
Path(__file__).stat().st_mtime
```

### os-path-getsize (PTH202)
Avoid uses of `os.path.getsize`.
❌ 
```
import os
os.path.getsize(__file__)
```
✅ 
```
from pathlib import Path
Path(__file__).stat().st_size
```

### os-path-isabs (PTH117)
Avoid uses of `os.path.isabs`.
❌ 
```
import os
if os.path.isabs(file_name):
    print("Absolute path!")
```
✅ 
```
from pathlib import Path
if Path(file_name).is_absolute():
    print("Absolute path!")
```

### os-path-isdir (PTH112)
Avoid uses of `os.path.isdir`.
❌ 
```
import os
os.path.isdir("docs")
```
✅ 
```
from pathlib import Path
Path("docs").is_dir()
```

### os-path-isfile (PTH113)
Avoid uses of `os.path.isfile`.
❌ 
```
import os
os.path.isfile("docs")
```
✅ 
```
from pathlib import Path
Path("docs").is_file()
```

### os-path-islink (PTH114)
Avoid uses of `os.path.islink`.
❌ 
```
import os
os.path.islink("docs")
```
✅ 
```
from pathlib import Path
Path("docs").is_symlink()
```

### os-path-join (PTH118)
Avoid uses of `os.path.join`.
❌ 
```
import os
os.path.join(os.path.join(ROOT_PATH, "folder"), "file.py")
```
✅ 
```
from pathlib import Path
Path(ROOT_PATH) / "folder" / "file.py"
```

### os-path-samefile (PTH121)
Avoid uses of `os.path.samefile`.
❌ 
```
import os
os.path.samefile("f1.py", "f2.py")
```
✅ 
```
from pathlib import Path
Path("f1.py").samefile("f2.py")
```

### os-path-splitext (PTH122)
Avoid uses of `os.path.splitext`.
❌ 
```
import os
(root, ext) = os.path.splitext("foo/bar.py")
```
✅ 
```
from pathlib import Path
path = Path("foo/bar.py")
root = path.parent / path.stem
ext = path.suffix
```

### os-readlink (PTH115)
Avoid uses of `os.readlink`.
❌ 
```
import os
os.readlink(file_name)
```
✅ 
```
from pathlib import Path
Path(file_name).readlink()
```

### os-remove (PTH107)
Avoid uses of `os.remove`.
❌ 
```
import os
os.remove("file.py")
```
✅ 
```
from pathlib import Path
Path("file.py").unlink()
```

### os-rename (PTH104)
Avoid uses of `os.rename`.
❌ 
```
import os
os.rename("old.py", "new.py")
```
✅ 
```
from pathlib import Path
Path("old.py").rename("new.py")
```

### os-replace (PTH105)
Avoid uses of `os.replace`.
❌ 
```
import os
os.replace("old.py", "new.py")
```
✅ 
```
from pathlib import Path
Path("old.py").replace("new.py")
```

### os-rmdir (PTH106)
Avoid uses of `os.rmdir`.
❌ 
```
import os
os.rmdir("folder/")
```
✅ 
```
from pathlib import Path
Path("folder/").rmdir()
```

### os-sep-split (PTH206)
Avoid uses of `.split(os.sep)`

### os-stat (PTH116)
Avoid uses of `os.stat`.
❌ 
```
import os
from pwd import getpwuid
from grp import getgrgid
stat = os.stat(file_name)
owner_name = getpwuid(stat.st_uid).pw_name
group_name = getgrgid(stat.st_gid).gr_name
```
✅ 
```
from pathlib import Path
file_path = Path(file_name)
stat = file_path.stat()
owner_name = file_path.owner()
group_name = file_path.group()
```

### os-symlink (PTH211)
Avoid uses of `os.symlink`.
❌ 
```
import os
os.symlink("usr/bin/python", "tmp/python", target_is_directory=False)
```
✅ 
```
from pathlib import Path
Path("tmp/python").symlink_to("usr/bin/python")
```

### os-unlink (PTH108)
Avoid uses of `os.unlink`.
❌ 
```
import os
os.unlink("file.py")
```
✅ 
```
from pathlib import Path
Path("file.py").unlink()
```

### path-constructor-current-directory (PTH201)
Avoid `pathlib.Path` objects that are initialized with the current directory.
❌ 
```
from pathlib import Path
_ = Path(".")
```
✅ 
```
from pathlib import Path
_ = Path()
```

### py-path (PTH124)
Avoid uses of the `py.path` library.
❌ 
```
import py.path
p = py.path.local("/foo/bar").join("baz/qux")
```
✅ 
```
from pathlib import Path
p = Path("/foo/bar") / "bar" / "qux"
```

### Plugin: `mccabe`

### complex-structure (C901)
Avoid functions with a high `McCabe` complexity.
❌ 
```
def foo(a, b, c):
    if a:
        if b:
            if c:
                return 1
            else:
…
```
✅ 
```
def foo(a, b, c):
    if not a:
        return 4
    if not b:
        return 3
    if not c:
…
```

### Plugin: `pyupgrade`

### convert-named-tuple-functional-to-class (UP014)
Avoid `NamedTuple` declarations that use functional syntax.
❌ 
```
from typing import NamedTuple
Foo = NamedTuple("Foo", [("a", int), ("b", str)])
```
✅ 
```
from typing import NamedTuple
class Foo(NamedTuple):
    a: int
    b: str
```

### convert-typed-dict-functional-to-class (UP013)
Avoid `TypedDict` declarations that use functional syntax.
❌ 
```
from typing import TypedDict
Foo = TypedDict("Foo", {"a": int, "b": str})
```
✅ 
```
from typing import TypedDict
class Foo(TypedDict):
    a: int
    b: str
```

### datetime-timezone-utc (UP017)
Avoid uses of `datetime.timezone.utc`.
❌ 
```
import datetime
datetime.timezone.utc
```
✅ 
```
import datetime
datetime.UTC
```

### deprecated-c-element-tree (UP023)
Avoid uses of the `xml.etree.cElementTree` module.
❌ `from xml.etree import cElementTree as ET`
✅ `from xml.etree import ElementTree as ET`

### deprecated-import (UP035)
Avoid uses of deprecated imports based on the minimum supported Python version.
❌ `from collections import Sequence`
✅ `from collections.abc import Sequence`

### deprecated-mock-import (UP026)
Avoid imports of the `mock` module that should be replaced with `unittest.mock`.
❌ `import mock`
✅ `from unittest import mock`

### deprecated-unittest-alias (UP005)
Avoid uses of deprecated methods from the `unittest` module.
❌ 
```
from unittest import TestCase
class SomeTest(TestCase):
    def test_something(self):
        self.assertEquals(1, 1)
```
✅ 
```
from unittest import TestCase
class SomeTest(TestCase):
    def test_something(self):
        self.assertEqual(1, 1)
```

### extraneous-parentheses (UP034)
Avoid extraneous parentheses.
❌ `print(("Hello, world"))`
✅ `print("Hello, world")`

### f-string (UP032)
Avoid `str.format` calls that can be replaced with f-strings.
❌ `"{}".format(foo)`
✅ `f"{foo}"`

### format-literals (UP030)
Avoid unnecessary positional indices in format strings.
❌ `"{0}, {1}".format("Hello", "World")  # "Hello, World"`
✅ `"{}, {}".format("Hello", "World")  # "Hello, World"`

### lru-cache-with-maxsize-none (UP033)
Avoid uses of `functools.lru_cache` that set `maxsize=None`.
❌ 
```
import functools
@functools.lru_cache(maxsize=None)
def foo(): ...
```
✅ 
```
import functools
@functools.cache
def foo(): ...
```

### lru-cache-without-parameters (UP011)
Avoid unnecessary parentheses on `functools.lru_cache` decorators.
❌ 
```
import functools
@functools.lru_cache()
def foo(): ...
```
✅ 
```
import functools
@functools.lru_cache
def foo(): ...
```

### native-literals (UP018)
Avoid unnecessary calls to `str`, `bytes`, `int`, `float`, `bool`, and `complex`.
❌ `str("foo")`
✅ `"foo"`

### non-pep585-annotation (UP006)
Avoid the use of generics that can be replaced with standard library variants based on PEP 585.
❌ 
```
from typing import List
foo: List[int] = [1, 2, 3]
```
✅ `foo: list[int] = [1, 2, 3]`

### non-pep604-annotation-optional (UP045)
Avoid `typing.Optional` annotations that can be rewritten based on PEP 604 syntax.
❌ 
```
from typing import Optional
foo: Optional[int] = None
```
✅ `foo: int | None = None`

### non-pep604-annotation-union (UP007)
Avoid type annotations that can be rewritten based on PEP 604 syntax.
❌ 
```
from typing import Union
foo: Union[int, str] = 1
```
✅ `foo: int | str = 1`

### non-pep604-isinstance (UP038)
Avoid uses of `isinstance` and `issubclass` that take a tuple of types for comparison.
❌ `isinstance(x, (int, float))`
✅ `isinstance(x, int | float)`

### non-pep646-unpack (UP044)
Avoid uses of `Unpack[]` on Python 3.11 and above, and suggests using `*` instead.
❌ 
```
from typing import Unpack
def foo(*args: Unpack[tuple[int, ...]]) -> None:
    pass
```
✅ 
```
def foo(*args: *tuple[int, ...]) -> None:
    pass
```

### non-pep695-generic-class (UP046)
Avoid use of standalone type variables and parameter specifications in generic classes.
❌ 
```
from typing import Generic, TypeVar
T = TypeVar("T")
class GenericClass(Generic[T]):
    var: T
```
✅ 
```
class GenericClass[T]:
    var: T
```

### non-pep695-generic-function (UP047)
Avoid use of standalone type variables and parameter specifications in generic functions.
❌ 
```
from typing import TypeVar
T = TypeVar("T")
def generic_function(var: T) -> T:
    return var
```
✅ 
```
def generic_function[T](var: T) -> T:
    return var
```

### non-pep695-type-alias (UP040)
Avoid use of `TypeAlias` annotations and `TypeAliasType` assignments for declaring type aliases.
❌ 
```
from typing import Annotated, TypeAlias, TypeAliasType
from annotated_types import Gt
ListOfInt: TypeAlias = list[int]
PositiveInt = TypeAliasType("PositiveInt", Annotated[int, Gt(0)])
```
✅ 
```
from typing import Annotated
from annotated_types import Gt
type ListOfInt = list[int]
type PositiveInt = Annotated[int, Gt(0)]
```

### open-alias (UP020)
Avoid uses of `io.open`.
❌ 
```
import io
with io.open("file.txt") as f:
    ...
```
✅ 
```
with open("file.txt") as f:
    ...
```

### os-error-alias (UP024)
Avoid uses of exceptions that alias `OSError`.
❌ `raise IOError`
✅ `raise OSError`

### outdated-version-block (UP036)
Avoid conditional blocks gated on `sys.version_info` comparisons that are outdated for the minimum supported Python version.
❌ 
```
import sys
if sys.version_info < (3, 0):
    print("py2")
else:
    print("py3")
```
✅ `print("py3")`

### printf-string-formatting (UP031)
Avoid `printf`-style string formatting, and offers to replace it with `str.format` calls.
❌ `"%s, %s" % ("Hello", "World")  # "Hello, World"`
✅ `"{}, {}".format("Hello", "World")  # "Hello, World"`

### private-type-parameter (UP049)
Avoid use of PEP 695 type parameters with leading underscores in generic classes and functions.
❌ 
```
class GenericClass[_T]:
    var: _T
def generic_function[_T](var: _T) -> list[_T]:
    return var[0]
```
✅ 
```
class GenericClass[T]:
    var: T
def generic_function[T](var: T) -> list[T]:
    return var[0]
```

### quoted-annotation (UP037)
Avoid the presence of unnecessary quotes in type annotations.
❌ 
```
from __future__ import annotations
def foo(bar: "Bar") -> "Bar": ...
```
✅ 
```
from __future__ import annotations
def foo(bar: Bar) -> Bar: ...
```

### redundant-open-modes (UP015)
Avoid redundant `open` mode arguments.
❌ 
```
with open("foo.txt", "r") as f:
    ...
```
✅ 
```
with open("foo.txt") as f:
    ...
```

### replace-stdout-stderr (UP022)
Avoid uses of `subprocess.run` that send `stdout` and `stderr` to a pipe.
❌ 
```
import subprocess
subprocess.run(["foo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
```
✅ 
```
import subprocess
subprocess.run(["foo"], capture_output=True)
```

### replace-str-enum (UP042)
Avoid classes that inherit from both `str` and `enum.Enum`.
❌ 
```
import enum
class Foo(str, enum.Enum): ...
```
✅ 
```
import enum
class Foo(enum.StrEnum): ...
```

### replace-universal-newlines (UP021)
Avoid uses of `subprocess.run` that set the `universal_newlines` keyword argument.
❌ 
```
import subprocess
subprocess.run(["foo"], universal_newlines=True)
```
✅ 
```
import subprocess
subprocess.run(["foo"], text=True)
```

### super-call-with-parameters (UP008)
Avoid `super` calls that pass redundant arguments.
❌ 
```
class A:
    def foo(self):
        pass
class B(A):
    def bar(self):
        super(B, self).foo()
```
✅ 
```
class A:
    def foo(self):
        pass
class B(A):
    def bar(self):
        super().foo()
```

### timeout-error-alias (UP041)
Avoid uses of exceptions that alias `TimeoutError`.
❌ 
```
import asyncio
raise asyncio.TimeoutError
```
✅ `raise TimeoutError`

### type-of-primitive (UP003)
Avoid uses of `type` that take a primitive as an argument.
❌ `type(1)`
✅ `int`

### typing-text-str-alias (UP019)
Avoid uses of `typing.Text`.
❌ 
```
from typing import Text
foo: Text = "bar"
```
✅ `foo: str = "bar"`

### unicode-kind-prefix (UP025)
Avoid uses of the Unicode kind prefix (`u`) in strings.
❌ `u"foo"`
✅ `"foo"`

### unnecessary-builtin-import (UP029)
Avoid unnecessary imports of builtins.
❌ 
```
from builtins import str
str(1)
```
✅ `str(1)`

### unnecessary-class-parentheses (UP039)
Avoid class definitions that include unnecessary parentheses after the class name.
❌ 
```
class Foo():
    ...
```
✅ 
```
class Foo:
    ...
```

### unnecessary-default-type-args (UP043)
Avoid unnecessary default type arguments for `Generator` and `AsyncGenerator` on Python 3.13+.
❌ 
```
from collections.abc import Generator, AsyncGenerator
def sync_gen() -> Generator[int, None, None]:
    yield 42
async def async_gen() -> AsyncGenerator[int, None]:
    yield 42
```
✅ 
```
from collections.abc import Generator, AsyncGenerator
def sync_gen() -> Generator[int]:
    yield 42
async def async_gen() -> AsyncGenerator[int]:
    yield 42
```

### unnecessary-encode-utf8 (UP012)
Avoid unnecessary calls to `encode` as UTF-8.
❌ `"foo".encode("utf-8")`
✅ `b"foo"`

### unnecessary-future-import (UP010)
Avoid unnecessary `__future__` imports.
❌ 
```
from __future__ import print_function
print("Hello, world!")
```
✅ `print("Hello, world!")`

### unpacked-list-comprehension (UP027)
Avoid list comprehensions that are immediately unpacked.
❌ `a, b, c = [foo(x) for x in items]`
✅ `a, b, c = (foo(x) for x in items)`

### useless-class-metaclass-type (UP050)
Avoid `metaclass=type` in class definitions.
❌ `class Foo(metaclass=type): ...`
✅ `class Foo: ...`

### useless-metaclass-type (UP001)
Avoid the use of `__metaclass__ = type` in class definitions.
❌ 
```
class Foo:
    __metaclass__ = type
```
✅ `class Foo: ...`

### useless-object-inheritance (UP004)
Avoid classes that inherit from `object`.
❌ `class Foo(object): ...`
✅ `class Foo: ...`

### utf8-encoding-declaration (UP009)
Avoid unnecessary UTF-8 encoding declarations.

### yield-in-for-loop (UP028)
Avoid `for` loops that can be replaced with `yield from` expressions.
❌ 
```
def bar():
    for x in foo:
        yield x
    global y
    for y in foo:
        yield y
```
✅ 
```
def bar():
    yield from foo
    for _element in foo:
        y = _element
        yield y
```
