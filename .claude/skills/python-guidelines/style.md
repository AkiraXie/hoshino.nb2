# Python Style & Pedantic Rules

275 opinionated style rules. Load this file only when:

- Reviewing existing code, or
- Matching an explicit project style guide, or
- The project has a lint config pinning these.

Do **not** load preemptively when writing new code.

---

## Plugin: `Pylint`

### and-or-ternary (PLR1706)
Avoid uses of the known pre-Python 2.5 ternary syntax.
❌ 
```
x, y = 1, 2
maximum = x >= y and x or y
```
✅ 
```
x, y = 1, 2
maximum = x if x >= y else y
```

### assert-on-string-literal (PLW0129)
Avoid `assert` statements that use a string literal as the first argument.
❌ `assert "always true"`

### bad-dunder-method-name (PLW3201)
Avoid dunder methods that have no special meaning in Python 3.
❌ 
```
class Foo:
    def __init_(self): ...
```
✅ 
```
class Foo:
    def __init__(self): ...
```

### bad-open-mode (PLW1501)
Avoid an invalid `mode` argument in `open` calls.
❌ 
```
with open("file", "rwx") as f:
    content = f.read()
```
✅ 
```
with open("file", "r") as f:
    content = f.read()
```

### bad-staticmethod-argument (PLW0211)
Avoid static methods that use `self` or `cls` as their first argument.
❌ 
```
class Wolf:
    @staticmethod
    def eat(self):
        pass
```
✅ 
```
class Wolf:
    @staticmethod
    def eat(sheep):
        pass
```

### binary-op-exception (PLW0711)
Avoid `except` clauses that attempt to catch multiple exceptions with a binary operation (`and` or `or`).
❌ 
```
try:
    pass
except A or B:
    pass
```
✅ 
```
try:
    pass
except (A, B):
    pass
```

### boolean-chained-comparison (PLR1716)
Avoid chained boolean operations that can be simplified.
❌ 
```
a = int(input())
b = int(input())
c = int(input())
if a < b and b < c:
    pass
```
✅ 
```
a = int(input())
b = int(input())
c = int(input())
if a < b < c:
    pass
```

### collapsible-else-if (PLR5501)
Avoid `else` blocks that consist of a single `if` statement.
❌ 
```
def check_sign(value: int) -> None:
    if value > 0:
        print("Number is positive.")
    else:
        if value < 0:
            print("Number is negative.")
…
```
✅ 
```
def check_sign(value: int) -> None:
    if value > 0:
        print("Number is positive.")
    elif value < 0:
        print("Number is negative.")
    else:
…
```

### compare-to-empty-string (PLC1901)
Avoid comparisons to empty strings.
❌ 
```
x: str = ...
if x == "":
    print("x is empty")
```
✅ 
```
x: str = ...
if not x:
    print("x is empty")
```

### comparison-of-constant (PLR0133)
Avoid comparisons between constants.
❌ `foo = 1 == 1`
✅ `foo = True`

### comparison-with-itself (PLR0124)
Avoid operations that compare a name to itself.
❌ `foo == foo`

### dict-index-missing-items (PLC0206)
Avoid dictionary iterations that extract the dictionary value via explicit indexing, instead of using `.items()`.
❌ 
```
ORCHESTRA = {
    "violin": "strings",
    "oboe": "woodwind",
    "tuba": "brass",
    "gong": "percussion",
}
…
```
✅ 
```
ORCHESTRA = {
    "violin": "strings",
    "oboe": "woodwind",
    "tuba": "brass",
    "gong": "percussion",
}
…
```

### empty-comment (PLR2044)
Avoid a # symbol appearing on a line not followed by an actual comment.
❌ 
```
class Foo:  #
    pass
```
✅ 
```
class Foo:
    pass
```

### eq-without-hash (PLW1641)
Avoid classes that implement `__eq__` but not `__hash__`.
❌ 
```
class Person:
    def __init__(self):
        self.name = "monty"
    def __eq__(self, other):
        return isinstance(other, Person) and other.name == self.name
```
✅ 
```
class Person:
    def __init__(self):
        self.name = "monty"
    def __eq__(self, other):
        return isinstance(other, Person) and other.name == self.name
    def __hash__(self):
…
```

### global-at-module-level (PLW0604)
Avoid uses of the `global` keyword at the module level.

### global-statement (PLW0603)
Avoid the use of `global` statements to update identifiers.
❌ 
```
var = 1
def foo():
    global var  # [global-statement]
    var = 10
    print(var)
foo()
…
```
✅ 
```
var = 1
def foo():
    var = 10
    print(var)
    return var
var = foo()
…
```

### global-variable-not-assigned (PLW0602)
Avoid `global` variables that are not assigned a value in the current scope.
❌ 
```
DEBUG = True
def foo():
    global DEBUG
    if DEBUG:
        print("foo() called")
    ...
```
✅ 
```
DEBUG = True
def foo():
    if DEBUG:
        print("foo() called")
    ...
```

### if-stmt-min-max (PLR1730)
Avoid `if` statements that can be replaced with `min()` or `max()` calls.
❌ 
```
if score > highest_score:
    highest_score = score
```
✅ `highest_score = max(highest_score, score)`

### import-outside-top-level (PLC0415)
Avoid `import` statements outside of a module's top-level scope, such as within a function or class definition.
❌ 
```
def print_python_version():
    import platform
    print(platform.python_version())
```
✅ 
```
import platform
def print_python_version():
    print(platform.python_version())
```

### import-private-name (PLC2701)
Avoid import statements that import a private name (a name starting with an underscore `_`) from another module.
❌ `from foo import _bar`

### import-self (PLW0406)
Avoid import statements that import the current module.

### invalid-envvar-default (PLW1508)
Avoid `os.getenv` calls with invalid default values.
❌ 
```
import os
int(os.getenv("FOO", 1))
```
✅ 
```
import os
int(os.getenv("FOO", "1"))
```

### iteration-over-set (PLC0208)
Avoid iteration over a `set` literal in which each element is a literal.
❌ 
```
for number in {1, 2, 3}:
    ...
```
✅ 
```
for number in (1, 2, 3):
    ...
```

### len-test (PLC1802)
Avoid `len` calls on sequences in a boolean test context.
❌ 
```
fruits = ["orange", "apple"]
vegetables = []
if len(fruits):
    print(fruits)
if not len(vegetables):
    print(vegetables)
```
✅ 
```
fruits = ["orange", "apple"]
vegetables = []
if fruits:
    print(fruits)
if not vegetables:
    print(vegetables)
```

### literal-membership (PLR6201)
Avoid membership tests on `list` and `tuple` literals.
❌ `1 in [1, 2, 3]`
✅ `1 in {1, 2, 3}`

### magic-value-comparison (PLR2004)
Avoid the use of unnamed numerical constants ("magic") values in comparisons.
❌ 
```
def apply_discount(price: float) -> float:
    if price <= 100:
        return price / 2
    else:
        return price
```
✅ 
```
MAX_DISCOUNT = 100
def apply_discount(price: float) -> float:
    if price <= MAX_DISCOUNT:
        return price / 2
    else:
        return price
```

### manual-from-import (PLR0402)
Avoid submodule imports that are aliased to the submodule name.
❌ `import concurrent.futures as futures`
✅ `from concurrent import futures`

### missing-maxsplit-arg (PLC0207)
Avoid access to the first or last element of `str.split()` or `str.rsplit()` without a `maxsplit=1` argument.
❌ 
```
url = "www.example.com"
prefix = url.split(".")[0]
```
✅ 
```
url = "www.example.com"
prefix = url.split(".", maxsplit=1)[0]
```

### named-expr-without-context (PLW0131)
Avoid uses of named expressions (e.g., `a := 42`) that can be replaced by regular assignment statements (e.g., `a = 42`).
❌ `(a := 42)`
✅ `a = 42`

### nan-comparison (PLW0177)
Avoid comparisons against NaN values.
❌ 
```
if x == float("NaN"):
    pass
```
✅ 
```
import math
if math.isnan(x):
    pass
```

### nested-min-max (PLW3301)
Avoid nested `min` and `max` calls.
❌ 
```
minimum = min(1, 2, min(3, 4, 5))
maximum = max(1, 2, max(3, 4, 5))
diff = maximum - minimum
```
✅ 
```
minimum = min(1, 2, 3, 4, 5)
maximum = max(1, 2, 3, 4, 5)
diff = maximum - minimum
```

### no-classmethod-decorator (PLR0202)
Avoid the use of a classmethod being made without the decorator.
❌ 
```
class Foo:
    def bar(cls): ...
    bar = classmethod(bar)
```
✅ 
```
class Foo:
    @classmethod
    def bar(cls): ...
```

### no-self-use (PLR6301)
Avoid the presence of unused `self` parameter in methods definitions.
❌ 
```
class Person:
    def greeting(self):
        print("Greetings friend!")
```
✅ 
```
def greeting():
    print("Greetings friend!")
```

### no-staticmethod-decorator (PLR0203)
Avoid the use of a staticmethod being made without the decorator.
❌ 
```
class Foo:
    def bar(arg1, arg2): ...
    bar = staticmethod(bar)
```
✅ 
```
class Foo:
    @staticmethod
    def bar(arg1, arg2): ...
```

### non-ascii-import-name (PLC2403)
Avoid the use of non-ASCII characters in import statements.
❌ `import bár`
✅ `import bar`

### non-ascii-name (PLC2401)
Avoid the use of non-ASCII characters in variable names.
❌ `ápple_count: int`
✅ `apple_count: int`

### non-augmented-assignment (PLR6104)
Avoid assignments that can be replaced with augmented assignment statements.
❌ `x = x + 1`
✅ `x += 1`

### property-with-parameters (PLR0206)
Avoid property definitions that accept function parameters.
❌ 
```
class Cat:
    @property
    def purr(self, volume): ...
```
✅ 
```
class Cat:
    @property
    def purr(self): ...
    def purr_volume(self, volume): ...
```

### redeclared-assigned-name (PLW0128)
Avoid declared assignments to the same variable multiple times in the same assignment.
❌ 
```
a, b, a = (1, 2, 3)
print(a)  # 3
```

### redefined-argument-from-local (PLR1704)
Avoid variables defined in `for`, `try`, `with` statements that redefine function parameters.
❌ 
```
def show(host_id=10.11):
    for host_id, host in [[12.13, "Venus"], [14.15, "Mars"]]:
        print(host_id, host)
```
✅ 
```
def show(host_id=10.11):
    for inner_host_id, host in [[12.13, "Venus"], [14.15, "Mars"]]:
        print(host_id, inner_host_id, host)
```

### redefined-loop-name (PLW2901)
Avoid variables defined in `for` loops and `with` statements that get overwritten within the body, for example by another `for` loop or `with` statement or by direct assignment.
❌ 
```
for i in range(10):
    i = 9
    print(i)  # prints 9 every iteration
for i in range(10):
    for i in range(10):  # original value overwritten
        pass
…
```

### redefined-slots-in-subclass (PLW0244)
Avoid a re-defined slot in a subclass.
❌ 
```
class Base:
    __slots__ = ("a", "b")
class Subclass(Base):
    __slots__ = ("a", "d")  # slot "a" redefined
```
✅ 
```
class Base:
    __slots__ = ("a", "b")
class Subclass(Base):
    __slots__ = "d"
```

### repeated-equality-comparison (PLR1714)
Avoid repeated equality comparisons that can be rewritten as a membership test.
❌ `foo == "bar" or foo == "baz" or foo == "qux"`
✅ `foo in {"bar", "baz", "qux"}`

### repeated-isinstance-calls (PLR1701)
Avoid repeated `isinstance` calls on the same object.
❌ 
```
def is_number(x):
    return isinstance(x, int) or isinstance(x, float) or isinstance(x, complex)
```
✅ 
```
def is_number(x):
    return isinstance(x, (int, float, complex))
```

### self-assigning-variable (PLW0127)
Avoid self-assignment of variables.
❌ 
```
country = "Poland"
country = country
```
✅ `country = "Poland"`

### self-or-cls-assignment (PLW0642)
Avoid assignment of `self` and `cls` in instance and class methods respectively.
❌ 
```
class Version:
    def add(self, other):
        self = self + other
        return self
    @classmethod
    def superclass(cls):
…
```
✅ 
```
class Version:
    def add(self, other):
        new_version = self + other
        return new_version
    @classmethod
    def superclass(cls):
…
```

### shallow-copy-environ (PLW1507)
Avoid shallow `os.environ` copies.
❌ 
```
import copy
import os
env = copy.copy(os.environ)
```
✅ 
```
import os
env = os.environ.copy()
```

### single-string-slots (PLC0205)
Avoid single strings assigned to `__slots__`.
❌ 
```
class Person:
    __slots__: str = "name"
    def __init__(self, name: str) -> None:
        self.name = name
```
✅ 
```
class Person:
    __slots__: tuple[str, ...] = ("name",)
    def __init__(self, name: str) -> None:
        self.name = name
```

### stop-iteration-return (PLR1708)
Avoid explicit `raise StopIteration` in generator functions.
❌ 
```
def my_generator():
    yield 1
    yield 2
    raise StopIteration  # This causes RuntimeError at runtime
```
✅ 
```
def my_generator():
    yield 1
    yield 2
    return  # Use return instead
```

### subprocess-popen-preexec-fn (PLW1509)
Avoid uses of `subprocess.Popen` with a `preexec_fn` argument.
❌ 
```
import os, subprocess
subprocess.Popen(foo, preexec_fn=os.setsid)
subprocess.Popen(bar, preexec_fn=os.setpgid(0, 0))
```
✅ 
```
import subprocess
subprocess.Popen(foo, start_new_session=True)
subprocess.Popen(bar, process_group=0)  # Introduced in Python 3.11
```

### subprocess-run-without-check (PLW1510)
Avoid uses of `subprocess.run` without an explicit `check` argument.
❌ 
```
import subprocess
subprocess.run(["ls", "nonexistent"])  # No exception raised.
```
✅ 
```
import subprocess
subprocess.run(["ls", "nonexistent"], check=True)  # Raises exception.
```

### super-without-brackets (PLW0245)
Avoid attempts to use `super` without parentheses.
❌ 
```
class Animal:
    @staticmethod
    def speak():
        return "This animal says something."
class Dog(Animal):
    @staticmethod
…
```
✅ 
```
class Animal:
    @staticmethod
    def speak():
        return "This animal says something."
class Dog(Animal):
    @staticmethod
…
```

### swap-with-temporary-variable (PLR1712)
Avoid code that swaps two variables using a temporary variable.
❌ 
```
def function(x, y):
    if x > y:
        temp = x
        x = y
        y = temp
    assert x <= y
```
✅ 
```
def function(x, y):
    if x > y:
        x, y = y, x
    assert x <= y
```

### sys-exit-alias (PLR1722)
Avoid uses of the `exit()` and `quit()`.
❌ 
```
if __name__ == "__main__":
    exit()
```
✅ 
```
import sys
if __name__ == "__main__":
    sys.exit()
```

### too-many-arguments (PLR0913)
Avoid function definitions that include too many arguments.
❌ 
```
def calculate_position(x_pos, y_pos, z_pos, x_vel, y_vel, z_vel, time):
    new_x = x_pos + x_vel * time
    new_y = y_pos + y_vel * time
    new_z = z_pos + z_vel * time
    return new_x, new_y, new_z
```
✅ 
```
from typing import NamedTuple
class Vector(NamedTuple):
    x: float
    y: float
    z: float
def calculate_position(pos: Vector, vel: Vector, time: float) -> Vector:
…
```

### too-many-boolean-expressions (PLR0916)
Avoid too many Boolean expressions in an `if` statement.
❌ 
```
if a and b and c and d and e and f and g and h:
    ...
```

### too-many-branches (PLR0912)
Avoid functions or methods with too many branches, including (nested) `if`, `elif`, and `else` branches, `for` loops, `try`-`except` clauses, and `match` and `case` statements.
❌ 
```
def capital(country):
    if country == "Australia":
        return "Canberra"
    elif country == "Brazil":
        return "Brasilia"
    elif country == "Canada":
…
```
✅ 
```
def capital(country):
    capitals = {
        "Australia": "Canberra",
        "Brazil": "Brasilia",
        "Canada": "Ottawa",
        "England": "London",
…
```

### too-many-locals (PLR0914)
Avoid functions that include too many local variables.

### too-many-nested-blocks (PLR1702)
Avoid functions or methods with too many nested blocks.

### too-many-positional-arguments (PLR0917)
Avoid function definitions that include too many positional arguments.
❌ 
```
def plot(x, y, z, color, mark, add_trendline): ...
plot(1, 2, 3, "r", "*", True)
```
✅ 
```
def plot(x, y, z, *, color, mark, add_trendline): ...
plot(1, 2, 3, color="r", mark="*", add_trendline=True)
```

### too-many-public-methods (PLR0904)
Avoid classes with too many public methods By default, this rule allows up to 20 public methods, as configured by the `lint.pylint.max-public-methods` option.
❌ 
```
class Linter:
    def __init__(self):
        pass
    def pylint(self):
        pass
    def pylint_settings(self):
…
```
✅ 
```
class Linter:
    def __init__(self):
        self.pylint = Pylint()
        self.flake8 = Flake8()
        self.pydocstyle = Pydocstyle()
    def lint(self):
…
```

### too-many-return-statements (PLR0911)
Avoid functions or methods with too many return statements.
❌ 
```
def capital(country: str) -> str | None:
    if country == "England":
        return "London"
    elif country == "France":
        return "Paris"
    elif country == "Poland":
…
```
✅ 
```
def capital(country: str) -> str | None:
    capitals = {
        "England": "London",
        "France": "Paris",
        "Poland": "Warsaw",
        "Romania": "Bucharest",
…
```

### too-many-statements (PLR0915)
Avoid functions or methods with too many statements.
❌ 
```
def is_even(number: int) -> bool:
    if number == 0:
        return True
    elif number == 1:
        return False
    elif number == 2:
…
```
✅ 
```
def is_even(number: int) -> bool:
    return number % 2 == 0
```

### type-bivariance (PLC0131)
Avoid `TypeVar` and `ParamSpec` definitions in which the type is both covariant and contravariant.
❌ 
```
from typing import TypeVar
T = TypeVar("T", covariant=True, contravariant=True)
```
✅ 
```
from typing import TypeVar
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)
```

### type-name-incorrect-variance (PLC0105)
Avoid type names that do not match the variance of their associated type parameter.
❌ 
```
from typing import TypeVar
T = TypeVar("T", covariant=True)
U = TypeVar("U", contravariant=True)
V_co = TypeVar("V_co")
```
✅ 
```
from typing import TypeVar
T_co = TypeVar("T_co", covariant=True)
U_contra = TypeVar("U_contra", contravariant=True)
V = TypeVar("V")
```

### type-param-name-mismatch (PLC0132)
Avoid `TypeVar`, `TypeVarTuple`, `ParamSpec`, and `NewType` definitions in which the name of the type parameter does not match the name of the variable to which it is assigned.
❌ 
```
from typing import TypeVar
T = TypeVar("U")
```
✅ 
```
from typing import TypeVar
T = TypeVar("T")
```

### unnecessary-dict-index-lookup (PLR1733)
Avoid key-based dict accesses during `.items()` iterations.
❌ 
```
FRUITS = {"apple": 1, "orange": 10, "berry": 22}
for fruit_name, fruit_count in FRUITS.items():
    print(FRUITS[fruit_name])
```
✅ 
```
FRUITS = {"apple": 1, "orange": 10, "berry": 22}
for fruit_name, fruit_count in FRUITS.items():
    print(fruit_count)
```

### unnecessary-direct-lambda-call (PLC3002)
Avoid unnecessary direct calls to lambda expressions.
❌ `area = (lambda r: 3.14 * r**2)(radius)`
✅ `area = 3.14 * radius**2`

### unnecessary-dunder-call (PLC2801)
Avoid explicit use of dunder methods, like `__str__` and `__add__`.
❌ 
```
three = (3.0).__str__()
twelve = "1".__add__("2")
def is_greater_than_two(x: int) -> bool:
    return x.__gt__(2)
```
✅ 
```
three = str(3.0)
twelve = "1" + "2"
def is_greater_than_two(x: int) -> bool:
    return x > 2
```

### unnecessary-lambda (PLW0108)
Avoid `lambda` definitions that consist of a single function call with the same arguments as the `lambda` itself.
❌ `df.apply(lambda x: str(x))`
✅ `df.apply(str)`

### unnecessary-list-index-lookup (PLR1736)
Avoid index-based list accesses during `enumerate` iterations.
❌ 
```
letters = ["a", "b", "c"]
for index, letter in enumerate(letters):
    print(letters[index])
```
✅ 
```
letters = ["a", "b", "c"]
for index, letter in enumerate(letters):
    print(letter)
```

### unspecified-encoding (PLW1514)
Avoid uses of `open` and related calls without an explicit `encoding` argument.
❌ `open("file.txt")`
✅ `open("file.txt", encoding="utf-8")`

### useless-else-on-loop (PLW0120)
Avoid `else` clauses on loops without a `break` statement.
❌ 
```
for item in items:
    print(item)
else:
    print("All items printed")
```
✅ 
```
for item in items:
    print(item)
print("All items printed")
```

### useless-exception-statement (PLW0133)
Avoid an exception that is not raised.
❌ `ValueError("...")`
✅ `raise ValueError("...")`

### useless-import-alias (PLC0414)
Avoid import aliases that do not rename the original package.
❌ `import numpy as numpy`
✅ `import numpy as np`

### useless-return (PLR1711)
Avoid functions that end with an unnecessary `return` or `return None`, and contain no other `return` statements.
❌ 
```
def f():
    print(5)
    return None
```
✅ 
```
def f():
    print(5)
```

### useless-with-lock (PLW2101)
Avoid lock objects that are created and immediately discarded in `with` statements.
❌ 
```
import threading
counter = 0
def increment():
    global counter
    with threading.Lock():
        counter += 1
```
✅ 
```
import threading
counter = 0
lock = threading.Lock()
def increment():
    global counter
    with lock:
…
```


## Plugin: `eradicate`

### commented-out-code (ERA001)
Avoid commented-out Python code.


## Plugin: `flake8-annotations`

### any-type (ANN401)
Ensure function arguments are annotated with a more specific type than `Any`.
❌ 
```
from typing import Any
def foo(x: Any): ...
```
✅ `def foo(x: int): ...`

### missing-return-type-class-method (ANN206)
Ensure class methods have return type annotations.
❌ 
```
class Foo:
    @classmethod
    def bar(cls):
        return 1
```
✅ 
```
class Foo:
    @classmethod
    def bar(cls) -> int:
        return 1
```

### missing-return-type-private-function (ANN202)
Ensure private functions and methods have return type annotations.
❌ 
```
def _add(a, b):
    return a + b
```
✅ 
```
def _add(a: int, b: int) -> int:
    return a + b
```

### missing-return-type-special-method (ANN204)
Ensure "special" methods, like `__init__`, `__new__`, and `__call__`, have return type annotations.
❌ 
```
class Foo:
    def __init__(self, x: int):
        self.x = x
```
✅ 
```
class Foo:
    def __init__(self, x: int) -> None:
        self.x = x
```

### missing-return-type-static-method (ANN205)
Ensure static methods have return type annotations.
❌ 
```
class Foo:
    @staticmethod
    def bar():
        return 1
```
✅ 
```
class Foo:
    @staticmethod
    def bar() -> int:
        return 1
```

### missing-return-type-undocumented-public-function (ANN201)
Ensure public functions and methods have return type annotations.
❌ 
```
def add(a, b):
    return a + b
```
✅ 
```
def add(a: int, b: int) -> int:
    return a + b
```

### missing-type-args (ANN002)
Ensure function `*args` arguments have type annotations.
❌ `def foo(*args): ...`
✅ `def foo(*args: int): ...`

### missing-type-cls (ANN102)
Ensure class method `cls` arguments have type annotations.
❌ 
```
class Foo:
    @classmethod
    def bar(cls): ...
```
✅ 
```
class Foo:
    @classmethod
    def bar(cls: Type["Foo"]): ...
```

### missing-type-function-argument (ANN001)
Ensure function arguments have type annotations.
❌ `def foo(x): ...`
✅ `def foo(x: int): ...`

### missing-type-kwargs (ANN003)
Ensure function `**kwargs` arguments have type annotations.
❌ `def foo(**kwargs): ...`
✅ `def foo(**kwargs: int): ...`

### missing-type-self (ANN101)
Ensure instance method `self` arguments have type annotations.
❌ 
```
class Foo:
    def bar(self): ...
```
✅ 
```
class Foo:
    def bar(self: "Foo"): ...
```


## Plugin: `flake8-boolean-trap`

### boolean-default-value-positional-argument (FBT002)
Avoid the use of boolean positional arguments in function definitions, as determined by the presence of a boolean default value.
❌ 
```
from math import ceil, floor
def round_number(number, up=True):
    return ceil(number) if up else floor(number)
round_number(1.5, True)  # What does `True` mean?
round_number(1.5, False)  # What does `False` mean?
```

### boolean-positional-value-in-call (FBT003)
Avoid boolean positional arguments in function calls.
❌ 
```
def func(flag: bool) -> None: ...
func(True)
```
✅ 
```
def func(flag: bool) -> None: ...
func(flag=True)
```

### boolean-type-hint-positional-argument (FBT001)
Avoid the use of boolean positional arguments in function definitions, as determined by the presence of a type hint containing `bool` as an evident subtype - e.g.
❌ 
```
from math import ceil, floor
def round_number(number: float, up: bool) -> int:
    return ceil(number) if up else floor(number)
round_number(1.5, True)  # What does `True` mean?
round_number(1.5, False)  # What does `False` mean?
```


## Plugin: `flake8-builtins`

### builtin-argument-shadowing (A002)
Avoid function arguments that use the same names as builtins.
❌ 
```
def remove_duplicates(list, list2):
    result = set()
    for value in list:
        result.add(value)
    for value in list2:
        result.add(value)
…
```
✅ 
```
def remove_duplicates(list1, list2):
    result = set()
    for value in list1:
        result.add(value)
    for value in list2:
        result.add(value)
…
```

### builtin-attribute-shadowing (A003)
Avoid class attributes and methods that use the same names as Python builtins.
❌ 
```
class Class:
    @staticmethod
    def list() -> None:
        pass
    @staticmethod
    def repeat(value: int, times: int) -> list[int]:
…
```

### builtin-import-shadowing (A004)
Avoid imports that use the same names as builtins.
❌ 
```
from rich import print
print("Some message")
```
✅ 
```
from rich import print as rich_print
rich_print("Some message")
```

### builtin-lambda-argument-shadowing (A006)
Avoid lambda arguments that use the same names as Python builtins.

### builtin-variable-shadowing (A001)
Avoid variable (and function) assignments that use the same names as builtins.
❌ 
```
def find_max(list_of_lists):
    max = 0
    for flat_list in list_of_lists:
        for value in flat_list:
            max = max(max, value)  # TypeError: 'int' object is not callable
    return max
```
✅ 
```
def find_max(list_of_lists):
    result = 0
    for flat_list in list_of_lists:
        for value in flat_list:
            result = max(result, value)
    return result
```

### stdlib-module-shadowing (A005)
Avoid modules that use the same names as Python standard-library modules.
❌ 
```
$ touch random.py
$ python3 -c 'from random import choice'
Traceback (most recent call last):
  File "<string>", line 1, in <module>
    from random import choice
ImportError: cannot import name 'choice' from 'random' (consider renaming '/random.py' since it has the same name as the standard library module named 'random' and prevents importing that standard library module)
```


## Plugin: `flake8-commas`

### missing-trailing-comma (COM812)
Avoid the absence of trailing commas.
❌ 
```
foo = {
    "bar": 1,
    "baz": 2
}
```
✅ 
```
foo = {
    "bar": 1,
    "baz": 2,
}
```

### prohibited-trailing-comma (COM819)
Avoid the presence of prohibited trailing commas.
❌ `foo = (1, 2, 3,)`
✅ `foo = (1, 2, 3)`

### trailing-comma-on-bare-tuple (COM818)
Avoid the presence of trailing commas on bare (i.e., unparenthesized) tuples.
❌ 
```
import json
foo = json.dumps({"bar": 1}),
```
✅ 
```
import json
foo = json.dumps({"bar": 1})
```


## Plugin: `flake8-copyright`

### missing-copyright-notice (CPY001)
Avoid the absence of copyright notices within Python files.


## Plugin: `flake8-debugger`

### debugger (T100)
Avoid the presence of debugger calls and imports.
❌ 
```
def foo():
    breakpoint()
```


## Plugin: `flake8-executable`

### shebang-leading-whitespace (EXE004)
Avoid whitespace before a shebang directive.
❌ ` #!/usr/bin/env python3`
✅ `#!/usr/bin/env python3`

### shebang-missing-executable-file (EXE002)
Avoid executable `.py` files that do not have a shebang.

### shebang-missing-python (EXE003)
Avoid a shebang directive in `.py` files that does not contain `python`, `pytest`, or `uv run`.
❌ `#!/usr/bin/env bash`
✅ `#!/usr/bin/env python3`

### shebang-not-executable (EXE001)
Avoid a shebang directive in a file that is not executable.
❌ `#!/usr/bin/env python`

### shebang-not-first-line (EXE005)
Avoid a shebang directive that is not at the beginning of the file.
❌ 
```
foo = 1
#!/usr/bin/env python3
```
✅ 
```
#!/usr/bin/env python3
foo = 1
```


## Plugin: `flake8-fixme`

### line-contains-fixme (FIX001)
Avoid "FIXME" comments.
❌ 
```
def speed(distance, time):
    return distance / time  # FIXME: Raises ZeroDivisionError for time = 0.
```

### line-contains-hack (FIX004)
Avoid "HACK" comments.
❌ 
```
import os
def running_windows():  # HACK: Use platform module instead.
    try:
        os.mkdir("C:\\Windows\\System32\\")
    except FileExistsError:
        return True
…
```

### line-contains-todo (FIX002)
Avoid "TODO" comments.
❌ 
```
def greet(name):
    return f"Hello, {name}!"  # TODO: Add support for custom greetings.
```

### line-contains-xxx (FIX003)
Avoid "XXX" comments.
❌ 
```
def speed(distance, time):
    return distance / time  # XXX: Raises ZeroDivisionError for time = 0.
```


## Plugin: `flake8-implicit-str-concat`

### explicit-string-concatenation (ISC003)
Avoid string literals that are explicitly concatenated (using the `+` operator).
❌ 
```
z = (
    "The quick brown fox jumps over the lazy "
    + "dog"
)
```
✅ 
```
z = (
    "The quick brown fox jumps over the lazy "
    "dog"
)
```

### implicit-string-concatenation-in-collection-literal (ISC004)
Avoid implicitly concatenated strings inside list, tuple, and set literals.
❌ 
```
facts = (
    "Lobsters have blue blood.",
    "The liver is the only human organ that can fully regenerate itself.",
    "Clarinets are made almost entirely out of wood from the mpingo tree."
    "In 1971, astronaut Alan Shepard played golf on the moon.",
)
```

### multi-line-implicit-string-concatenation (ISC002)
Avoid implicitly concatenated strings that span multiple lines.
❌ 
```
z = "The quick brown fox jumps over the lazy "\
    "dog."
```
✅ 
```
z = (
    "The quick brown fox jumps over the lazy "
    "dog."
)
```

### single-line-implicit-string-concatenation (ISC001)
Avoid implicitly concatenated strings on a single line.
❌ `z = "The quick " "brown fox."`
✅ `z = "The quick brown fox."`


## Plugin: `flake8-no-pep420`

### implicit-namespace-package (INP001)
Avoid packages that are missing an `__init__.py` file.


## Plugin: `flake8-print`

### p-print (T203)
Avoid `pprint` statements.
❌ 
```
import pprint
def merge_dicts(dict_a, dict_b):
    dict_c = {**dict_a, **dict_b}
    pprint.pprint(dict_c)
    return dict_c
```
✅ 
```
def merge_dicts(dict_a, dict_b):
    dict_c = {**dict_a, **dict_b}
    return dict_c
```

### print (T201)
Avoid `print` statements.
❌ 
```
def sum_less_than_four(a, b):
    print(f"Calling sum_less_than_four")
    return a + b < 4
```


## Plugin: `flake8-quotes`

### avoidable-escaped-quote (Q003)
Avoid strings that include escaped quotes, and suggests changing the quote style to avoid the need to escape them.
❌ `foo = "bar\"s"`
✅ `foo = 'bar"s'`

### bad-quotes-docstring (Q002)
Avoid docstrings that use single quotes or double quotes, depending on the value of the `lint.flake8-quotes.docstring-quotes` setting.
❌ 
```
'''
bar
'''
```

### bad-quotes-inline-string (Q000)
Avoid inline strings that use single quotes or double quotes, depending on the value of the `lint.flake8-quotes.inline-quotes` option.
❌ `foo = 'bar'`

### bad-quotes-multiline-string (Q001)
Avoid multiline strings that use single quotes or double quotes, depending on the value of the `lint.flake8-quotes.multiline-quotes` setting.
❌ 
```
foo = '''
bar
'''
```

### unnecessary-escaped-quote (Q004)
Avoid strings that include unnecessarily escaped quotes.
❌ `foo = "bar\'s"`
✅ `foo = "bar's"`


## Plugin: `flake8-todos`

### invalid-todo-capitalization (TD006)
Ensure a "TODO" tag is properly capitalized (i.e., that the tag is uppercase).

### invalid-todo-tag (TD001)
Ensure a TODO comment is labelled with "TODO".

### missing-space-after-todo-colon (TD007)
Ensure the colon after a "TODO" tag is followed by a space.

### missing-todo-author (TD002)
Ensure a TODO comment includes an author.

### missing-todo-colon (TD004)
Ensure a "TODO" tag is followed by a colon.

### missing-todo-description (TD005)
Ensure a "TODO" tag contains a description of the issue following the tag itself.

### missing-todo-link (TD003)
Ensure a TODO comment is associated with a link to a relevant issue or ticket.


## Plugin: `flake8-unused-arguments`

### unused-class-method-argument (ARG003)
Avoid the presence of unused arguments in class method definitions.
❌ 
```
class Class:
    @classmethod
    def foo(cls, arg1, arg2):
        print(arg1)
```
✅ 
```
class Class:
    @classmethod
    def foo(cls, arg1):
        print(arg1)
```

### unused-function-argument (ARG001)
Avoid the presence of unused arguments in function definitions.
❌ 
```
def foo(bar, baz):
    return bar * 2
```
✅ 
```
def foo(bar):
    return bar * 2
```

### unused-lambda-argument (ARG005)
Avoid the presence of unused arguments in lambda expression definitions.
❌ 
```
my_list = [1, 2, 3, 4, 5]
squares = map(lambda x, y: x**2, my_list)
```
✅ 
```
my_list = [1, 2, 3, 4, 5]
squares = map(lambda x: x**2, my_list)
```

### unused-method-argument (ARG002)
Avoid the presence of unused arguments in instance method definitions.
❌ 
```
class Class:
    def foo(self, arg1, arg2):
        print(arg1)
```
✅ 
```
class Class:
    def foo(self, arg1):
        print(arg1)
```

### unused-static-method-argument (ARG004)
Avoid the presence of unused arguments in static method definitions.
❌ 
```
class Class:
    @staticmethod
    def foo(arg1, arg2):
        print(arg1)
```
✅ 
```
class Class:
    @staticmethod
    def foo(arg1):
        print(arg1)
```


## Plugin: `isort`

### missing-required-import (I002)
Adds any required imports, as specified by the user, to the top of the file.
❌ `import typing`
✅ 
```
from __future__ import annotations
import typing
```

### unsorted-imports (I001)
De-duplicates, groups, and sorts imports based on the provided `isort` settings.
❌ 
```
import pandas
import numpy as np
```
✅ 
```
import numpy as np
import pandas
```


## Plugin: `pep8-naming`

### camelcase-imported-as-acronym (N817)
Avoid `CamelCase` imports that are aliased as acronyms.
❌ `from example import MyClassName as MCN`
✅ `from example import MyClassName`

### camelcase-imported-as-constant (N814)
Avoid `CamelCase` imports that are aliased to constant-style names.
❌ `from example import MyClassName as MY_CLASS_NAME`
✅ `from example import MyClassName`

### camelcase-imported-as-lowercase (N813)
Avoid `CamelCase` imports that are aliased to lowercase names.
❌ `from example import MyClassName as myclassname`
✅ `from example import MyClassName`

### constant-imported-as-non-constant (N811)
Avoid constant imports that are aliased to non-constant-style names.
❌ `from example import CONSTANT_VALUE as ConstantValue`
✅ `from example import CONSTANT_VALUE`

### dunder-function-name (N807)
Avoid functions with "dunder" names (that is, names with two leading and trailing underscores) that are not documented.
❌ 
```
def __my_function__():
    pass
```
✅ 
```
def my_function():
    pass
```

### error-suffix-on-exception-name (N818)
Avoid custom exception definitions that omit the `Error` suffix.
❌ `class Validation(Exception): ...`
✅ `class ValidationError(Exception): ...`

### invalid-argument-name (N803)
Avoid argument names that do not follow the `snake_case` convention.
❌ 
```
def my_function(A, myArg):
    pass
```
✅ 
```
def my_function(a, my_arg):
    pass
```

### invalid-class-name (N801)
Avoid class names that do not follow the `CamelCase` convention.
❌ 
```
class my_class:
    pass
```
✅ 
```
class MyClass:
    pass
```

### invalid-first-argument-name-for-class-method (N804)
Avoid class methods that use a name other than `cls` for their first argument.
❌ 
```
class Example:
    @classmethod
    def function(self, data): ...
```
✅ 
```
class Example:
    @classmethod
    def function(cls, data): ...
```

### invalid-first-argument-name-for-method (N805)
Avoid instance methods that use a name other than `self` for their first argument.
❌ 
```
class Example:
    def function(cls, data): ...
```
✅ 
```
class Example:
    def function(self, data): ...
```

### invalid-function-name (N802)
Avoid functions names that do not follow the `snake_case` naming convention.
❌ 
```
def myFunction():
    pass
```
✅ 
```
def my_function():
    pass
```

### invalid-module-name (N999)
Avoid module names that do not follow the `snake_case` naming convention or are otherwise invalid.

### lowercase-imported-as-non-lowercase (N812)
Avoid lowercase imports that are aliased to non-lowercase names.
❌ `from example import myclassname as MyClassName`
✅ `from example import myclassname`

### mixed-case-variable-in-class-scope (N815)
Avoid class variable names that follow the `mixedCase` convention.
❌ 
```
class MyClass:
    myVariable = "hello"
    another_variable = "world"
```
✅ 
```
class MyClass:
    my_variable = "hello"
    another_variable = "world"
```

### mixed-case-variable-in-global-scope (N816)
Avoid global variable names that follow the `mixedCase` convention.
❌ 
```
myVariable = "hello"
another_variable = "world"
yet_anotherVariable = "foo"
```
✅ 
```
my_variable = "hello"
another_variable = "world"
yet_another_variable = "foo"
```

### non-lowercase-variable-in-function (N806)
Avoid the use of non-lowercase variable names in functions.
❌ 
```
def my_function(a):
    B = a + 3
    return B
```
✅ 
```
def my_function(a):
    b = a + 3
    return b
```


## Plugin: `pycodestyle`

### ambiguous-class-name (E742)
Avoid the use of the characters 'l', 'O', or 'I' as class names.
❌ `class I(object): ...`
✅ `class Integer(object): ...`

### ambiguous-function-name (E743)
Avoid the use of the characters 'l', 'O', or 'I' as function names.
❌ `def l(x): ...`
✅ `def long_name(x): ...`

### ambiguous-variable-name (E741)
Avoid the use of the characters 'l', 'O', or 'I' as variable names.
❌ 
```
l = 0
O = 123
I = 42
```
✅ 
```
L = 0
o = 123
i = 42
```

### bare-except (E722)
Avoid bare `except` catches in `try`-`except` statements.
❌ 
```
try:
    raise KeyboardInterrupt("You probably don't mean to break CTRL-C.")
except:
    print("But a bare `except` will ignore keyboard interrupts.")
```
✅ 
```
try:
    do_something_that_might_break()
except MoreSpecificException as e:
    handle_error(e)
```

### blank-line-after-decorator (E304)
Avoid extraneous blank line(s) after function decorators.
❌ 
```
class User(object):
    @property
    def name(self):
        pass
```
✅ 
```
class User(object):
    @property
    def name(self):
        pass
```

### blank-line-between-methods (E301)
Avoid missing blank lines between methods of a class.
❌ 
```
class MyClass(object):
    def func1():
        pass
    def func2():
        pass
```
✅ 
```
class MyClass(object):
    def func1():
        pass
    def func2():
        pass
```

### blank-line-with-whitespace (W293)
Avoid superfluous whitespace in blank lines.
❌ `class Foo(object):\n    \n    bang = 12`
✅ `class Foo(object):\n\n    bang = 12`

### blank-lines-after-function-or-class (E305)
Avoid missing blank lines after the end of function or class.
❌ 
```
class User(object):
    pass
user = User()
```
✅ 
```
class User(object):
    pass
user = User()
```

### blank-lines-before-nested-definition (E306)
Avoid 1 blank line between nested function or class definitions.
❌ 
```
def outer():
    def inner():
        pass
    def inner2():
        pass
```
✅ 
```
def outer():
    def inner():
        pass
    def inner2():
        pass
```

### blank-lines-top-level (E302)
Avoid missing blank lines between top level functions and classes.
❌ 
```
def func1():
    pass
def func2():
    pass
```
✅ 
```
def func1():
    pass
def func2():
    pass
```

### doc-line-too-long (W505)
Avoid doc lines that exceed the specified maximum character length.
❌ 
```
def function(x):
    """Lorem ipsum dolor sit amet, consectetur adipiscing elit. Duis auctor purus ut ex fermentum, at maximus est hendrerit."""
```
✅ 
```
def function(x):
    """
    Lorem ipsum dolor sit amet, consectetur adipiscing elit.
    Duis auctor purus ut ex fermentum, at maximus est hendrerit.
    """
```

### indentation-with-invalid-multiple (E111)
Avoid indentation with a non-multiple of 4 spaces.
❌ 
```
if True:
   a = 1
```
✅ 
```
if True:
    a = 1
```

### indentation-with-invalid-multiple-comment (E114)
Avoid indentation of comments with a non-multiple of 4 spaces.
❌ 
```
if True:
   # a = 1
    ...
```
✅ 
```
if True:
    # a = 1
    ...
```

### invalid-escape-sequence (W605)
Avoid invalid escape sequences.
❌ `regex = "\.png$"`
✅ `regex = r"\.png$"`

### io-error (E902)
This is not a regular diagnostic; instead, it's raised when a file cannot be read from disk.
❌ 
```
$ echo 'print("hello world!")' > a.py
$ chmod 000 a.py
$ ruff a.py
a.py:1:1: E902 Permission denied (os error 13)
Found 1 error.
```

### lambda-assignment (E731)
Avoid lambda expressions which are assigned to a variable.
❌ `f = lambda x: 2 * x`
✅ 
```
def f(x):
    return 2 * x
```

### line-too-long (E501)
Avoid lines that exceed the specified maximum character length.
❌ `my_function(param1, param2, param3, param4, param5, param6, param7, param8, param9, param10)`
✅ 
```
my_function(
    param1, param2, param3, param4, param5,
    param6, param7, param8, param9, param10
)
```

### missing-newline-at-end-of-file (W292)
Avoid files missing a new line at the end of the file.
❌ `spam(1)`
✅ `spam(1)\n`

### missing-whitespace (E231)
Avoid missing whitespace after `,`, `;`, and `:`.
❌ `a = (1,2)`
✅ `a = (1, 2)`

### missing-whitespace-after-keyword (E275)
Avoid missing whitespace after keywords.
❌ 
```
if(True):
    pass
```
✅ 
```
if (True):
    pass
```

### missing-whitespace-around-arithmetic-operator (E226)
Avoid missing whitespace arithmetic operators.
❌ `number = 40+2`
✅ `number = 40 + 2`

### missing-whitespace-around-bitwise-or-shift-operator (E227)
Avoid missing whitespace around bitwise and shift operators.
❌ `x = 128<<1`
✅ `x = 128 << 1`

### missing-whitespace-around-modulo-operator (E228)
Avoid missing whitespace around the modulo operator.
❌ `remainder = 10%2`
✅ `remainder = 10 % 2`

### missing-whitespace-around-operator (E225)
Avoid missing whitespace around all operators.
❌ 
```
if number==42:
    print('you have found the meaning of life')
```
✅ 
```
if number == 42:
    print('you have found the meaning of life')
```

### missing-whitespace-around-parameter-equals (E252)
Avoid missing whitespace around the equals sign in an annotated function keyword parameter.
❌ 
```
def add(a: int=0) -> int:
    return a + 1
```
✅ 
```
def add(a: int = 0) -> int:
    return a + 1
```

### mixed-spaces-and-tabs (E101)
Avoid mixed tabs and spaces in indentation.
❌ `if a == 0:\n        a = 1\n\tb = 1`
✅ `if a == 0:\n    a = 1\n    b = 1`

### module-import-not-at-top-of-file (E402)
Avoid imports that are not at the top of the file.
❌ 
```
"One string"
"Two string"
a = 1
import os
from sys import x
```
✅ 
```
import os
from sys import x
"One string"
"Two string"
a = 1
```

### multiple-imports-on-one-line (E401)
Avoid multiple imports on one line.
❌ `import sys, os`
✅ 
```
import os
import sys
```

### multiple-leading-hashes-for-block-comment (E266)
Avoid block comments that start with multiple leading `#` characters.

### multiple-spaces-after-comma (E241)
Avoid extraneous whitespace after a comma.
❌ `a = 4,    5`
✅ `a = 4, 5`

### multiple-spaces-after-keyword (E271)
Avoid extraneous whitespace after keywords.
❌ `True and  False`
✅ `True and False`

### multiple-spaces-after-operator (E222)
Avoid extraneous whitespace after an operator.
❌ `a = 4 +  5`
✅ `a = 4 + 5`

### multiple-spaces-before-keyword (E272)
Avoid extraneous whitespace before keywords.
❌ `x  and y`
✅ `x and y`

### multiple-spaces-before-operator (E221)
Avoid extraneous whitespace before an operator.
❌ `a = 4  + 5`
✅ `a = 4 + 5`

### multiple-statements-on-one-line-colon (E701)
Avoid compound statements (multiple statements on the same line).
❌ `if foo == "blah": do_blah_thing()`
✅ 
```
if foo == "blah":
    do_blah_thing()
```

### multiple-statements-on-one-line-semicolon (E702)
Avoid multiline statements on one line.
❌ `do_one(); do_two(); do_three()`
✅ 
```
do_one()
do_two()
do_three()
```

### no-indented-block (E112)
Avoid indented blocks that are lacking indentation.
❌ 
```
for item in items:
pass
```
✅ 
```
for item in items:
    pass
```

### no-indented-block-comment (E115)
Avoid comments in a code blocks that are lacking indentation.

### no-space-after-block-comment (E265)
Avoid block comments that lack a single space after the leading `#` character.
❌ `#Block comment`

### no-space-after-inline-comment (E262)
If one space is used after inline comments.
❌ 
```
x = x + 1  #Increment x
x = x + 1  #  Increment x
x = x + 1  # \xa0Increment x
```
✅ 
```
x = x + 1  # Increment x
x = x + 1    # Increment x
```

### none-comparison (E711)
Avoid comparisons to `None` which are not using the `is` operator.
❌ 
```
if arg != None:
    pass
if None == arg:
    pass
```
✅ 
```
if arg is not None:
    pass
```

### not-in-test (E713)
Avoid membership tests using `not {element} in {collection}`.
❌ 
```
Z = not X in Y
if not X.B in Y:
    pass
```
✅ 
```
Z = X not in Y
if X.B not in Y:
    pass
```

### not-is-test (E714)
Avoid identity comparisons using `not {foo} is {bar}`.
❌ 
```
if not X is Y:
    pass
Z = not X.B is Y
```
✅ 
```
if X is not Y:
    pass
Z = X.B is not Y
```

### over-indented (E117)
Avoid over-indented code.
❌ 
```
for item in items:
      pass
```
✅ 
```
for item in items:
    pass
```

### redundant-backslash (E502)
Avoid redundant backslashes between brackets.
❌ 
```
x = (2 + \
    2)
```
✅ 
```
x = (2 +
    2)
```

### syntax-error (E999)
Avoid code that contains syntax errors.
❌ `x =`
✅ `x = 1`

### tab-after-comma (E242)
Avoid extraneous tabs after a comma.
❌ `a = 4,\t5`
✅ `a = 4, 5`

### tab-after-keyword (E273)
Avoid extraneous tabs after keywords.
❌ `True and\tFalse`
✅ `True and False`

### tab-after-operator (E224)
Avoid extraneous tabs after an operator.
❌ `a = 4 +\t5`
✅ `a = 4 + 5`

### tab-before-keyword (E274)
Avoid extraneous tabs before keywords.
❌ `True\tand False`
✅ `True and False`

### tab-before-operator (E223)
Avoid extraneous tabs before an operator.
❌ `a = 4\t+ 5`
✅ `a = 4 + 5`

### tab-indentation (W191)
Avoid indentation that uses tabs.

### too-few-spaces-before-inline-comment (E261)
If inline comments are separated by at least two spaces.
❌ `x = x + 1 # Increment x`
✅ 
```
x = x + 1  # Increment x
x = x + 1    # Increment x
```

### too-many-blank-lines (E303)
Avoid extraneous blank lines.
❌ 
```
def func1():
    pass
def func2():
    pass
```
✅ 
```
def func1():
    pass
def func2():
    pass
```

### too-many-newlines-at-end-of-file (W391)
Avoid files with multiple trailing blank lines.
❌ `spam(1)\n\n\n`
✅ `spam(1)\n`

### trailing-whitespace (W291)
Avoid superfluous trailing whitespace.
❌ `spam(1) \n#`
✅ `spam(1)\n#`

### true-false-comparison (E712)
Avoid equality comparisons to boolean literals.
❌ 
```
if foo == True:
    ...
if bar == False:
    ...
```
✅ 
```
if foo:
    ...
if not bar:
    ...
```

### type-comparison (E721)
Avoid object type comparisons using `==` and other comparison operators.
❌ 
```
if type(obj) == type(1):
    pass
if type(obj) == int:
    pass
```
✅ 
```
if isinstance(obj, int):
    pass
```

### unexpected-indentation (E113)
Avoid unexpected indentation.
❌ 
```
a = 1
    b = 2
```
✅ 
```
a = 1
b = 2
```

### unexpected-indentation-comment (E116)
Avoid unexpected indentation of comment.
❌ 
```
a = 1
    # b = 2
```

### unexpected-spaces-around-keyword-parameter-equals (E251)
Avoid missing whitespace around the equals sign in an unannotated function keyword parameter.
❌ 
```
def add(a = 0) -> int:
    return a + 1
```
✅ 
```
def add(a=0) -> int:
    return a + 1
```

### useless-semicolon (E703)
Avoid statements that end with an unnecessary semicolon.
❌ `do_four();  # useless semicolon`
✅ `do_four()`

### whitespace-after-decorator (E204)
Avoid trailing whitespace after a decorator's opening `@`.
❌ 
```
@ decorator
def func():
   pass
```
✅ 
```
@decorator
def func():
  pass
```

### whitespace-after-open-bracket (E201)
Avoid the use of extraneous whitespace after "(", "[" or "{".
❌ 
```
spam( ham[1], {eggs: 2})
spam(ham[ 1], {eggs: 2})
spam(ham[1], { eggs: 2})
```
✅ `spam(ham[1], {eggs: 2})`

### whitespace-before-close-bracket (E202)
Avoid the use of extraneous whitespace before ")", "]" or "}".
❌ 
```
spam(ham[1], {eggs: 2} )
spam(ham[1 ], {eggs: 2})
spam(ham[1], {eggs: 2 })
```
✅ `spam(ham[1], {eggs: 2})`

### whitespace-before-parameters (E211)
Avoid extraneous whitespace immediately preceding an open parenthesis or bracket.
❌ `spam (1)`
✅ `spam(1)`

### whitespace-before-punctuation (E203)
Avoid the use of extraneous whitespace before ",", ";" or ":".
❌ `if x == 4: print(x, y); x, y = y , x`
✅ `if x == 4: print(x, y); x, y = y, x`


## Plugin: `pydoclint`

### docstring-extraneous-exception (DOC502)
Avoid function docstrings that state that exceptions could be raised even though they are not directly raised in the function body.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    Returns:
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    Returns:
…
```

### docstring-extraneous-parameter (DOC102)
Avoid function docstrings that include parameters which are not in the function signature.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
        acceleration: Rate of change of speed.
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    Returns:
…
```

### docstring-extraneous-returns (DOC202)
Avoid function docstrings with unnecessary "Returns" sections.
❌ 
```
def say_hello(n: int) -> None:
    """Says hello to the user.
    Args:
        n: Number of times to say hello.
    Returns:
        Doesn't return anything.
…
```
✅ 
```
def say_hello(n: int) -> None:
    """Says hello to the user.
    Args:
        n: Number of times to say hello.
    """
    for _ in range(n):
…
```

### docstring-extraneous-yields (DOC403)
Avoid function docstrings with unnecessary "Yields" sections.
❌ 
```
def say_hello(n: int) -> None:
    """Says hello to the user.
    Args:
        n: Number of times to say hello.
    Yields:
        Doesn't yield anything.
…
```
✅ 
```
def say_hello(n: int) -> None:
    """Says hello to the user.
    Args:
        n: Number of times to say hello.
    """
    for _ in range(n):
…
```

### docstring-missing-exception (DOC501)
Avoid function docstrings that do not document all explicitly raised exceptions.
❌ 
```
class FasterThanLightError(ArithmeticError): ...
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
…
```
✅ 
```
class FasterThanLightError(ArithmeticError): ...
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
…
```

### docstring-missing-returns (DOC201)
Avoid functions with `return` statements that do not have "Returns" sections in their docstrings.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    """
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    Returns:
…
```

### docstring-missing-yields (DOC402)
Avoid functions with `yield` statements that do not have "Yields" sections in their docstrings.
❌ 
```
def count_to_n(n: int) -> int:
    """Generate integers up to *n*.
    Args:
        n: The number at which to stop counting.
    """
    for i in range(1, n + 1):
…
```
✅ 
```
def count_to_n(n: int) -> int:
    """Generate integers up to *n*.
    Args:
        n: The number at which to stop counting.
    Yields:
        int: The number we're at in the count.
…
```


## Plugin: `pydocstyle`

### blank-line-after-function (D202)
Avoid docstrings on functions that are separated by one or more blank lines from the function body.
❌ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
    return sum(values) / len(values)
```
✅ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
    return sum(values) / len(values)
```

### blank-line-before-class (D211)
Avoid docstrings on class definitions that are preceded by a blank line.
❌ 
```
class PhotoMetadata:
    """Metadata about a photo."""
```
✅ 
```
class PhotoMetadata:
    """Metadata about a photo."""
```

### blank-line-before-function (D201)
Avoid docstrings on functions that are separated by one or more blank lines from the function definition.
❌ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
```
✅ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
```

### blank-lines-between-header-and-content (D412)
Avoid docstring sections that contain blank lines between a section header and a section body.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    Returns:
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    Returns:
…
```

### docstring-starts-with-this (D404)
Avoid docstrings that start with `This`.
❌ 
```
def average(values: list[float]) -> float:
    """This function returns the mean of the given values."""
```
✅ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
```

### docstring-tab-indentation (D206)
Avoid docstrings that are indented with tabs.
❌ 
```
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the result using the bubble
    sort algorithm.
    """
```
✅ 
```
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the result using the bubble
    sort algorithm.
    """
```

### empty-docstring (D419)
Avoid empty docstrings.
❌ 
```
def average(values: list[float]) -> float:
    """"""
```
✅ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
```

### empty-docstring-section (D414)
Avoid docstrings with empty sections.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```

### escape-sequence-in-docstring (D301)
Avoid docstrings that include backslashes, but are not defined as raw string literals.
❌ 
```
def foobar():
    """Docstring for foo\bar."""
foobar.__doc__  # "Docstring for foar."
```
✅ 
```
def foobar():
    r"""Docstring for foo\bar."""
foobar.__doc__  # "Docstring for foo\bar."
```

### first-word-uncapitalized (D403)
Avoid docstrings that do not start with a capital letter.
❌ 
```
def average(values: list[float]) -> float:
    """return the mean of the given values."""
```
✅ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
```

### incorrect-blank-line-after-class (D204)
Avoid class methods that are not separated from the class's docstring by a blank line.
❌ 
```
class PhotoMetadata:
    """Metadata about a photo."""
    def __init__(self, file: Path):
        ...
```
✅ 
```
class PhotoMetadata:
    """Metadata about a photo."""
    def __init__(self, file: Path):
        ...
```

### incorrect-blank-line-before-class (D203)
Avoid docstrings on class definitions that are not preceded by a blank line.
❌ 
```
class PhotoMetadata:
    """Metadata about a photo."""
```
✅ 
```
class PhotoMetadata:
    """Metadata about a photo."""
```

### incorrect-section-order (D420)
Avoid docstring sections that appear out of order.
❌ 
```
def func() -> int:
    """Summary.
    Notes
    -----
    Some notes.
    Returns
…
```
✅ 
```
def func() -> int:
    """Summary.
    Returns
    -------
    int
    Notes
…
```

### mismatched-section-underline-length (D409)
Avoid section underlines in docstrings that do not match the length of the corresponding section header.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ---
    distance : float
        Distance traveled.
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```

### missing-blank-line-after-last-section (D413)
Avoid missing blank lines after the last section of a multiline docstring.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```

### missing-blank-line-after-summary (D205)
Avoid docstring summary lines that are not separated from the docstring description by one blank line.
❌ 
```
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the
    result using the bubble sort algorithm.
    """
```
✅ 
```
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the
    result using the bubble sort algorithm.
    """
```

### missing-dashed-underline-after-section (D407)
Avoid section headers in docstrings that are not followed by underlines.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    distance : float
        Distance traveled.
    time : float
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```

### missing-new-line-after-section-name (D406)
Avoid section headers in docstrings that are followed by non-newline characters.

### missing-section-name-colon (D416)
Avoid docstring section headers that do not end with a colon.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args
        distance: Distance traveled.
        time: Time spent traveling.
    Returns
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    Returns:
…
```

### missing-section-underline-after-name (D408)
Avoid section underlines in docstrings that are not on the line immediately following the section name.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```

### missing-terminal-punctuation (D415)
Avoid docstrings in which the first line does not end in a punctuation mark, such as a period, question mark, or exclamation point.
❌ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values"""
```
✅ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
```

### missing-trailing-period (D400)
Avoid docstrings in which the first line does not end in a period.
❌ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values"""
```
✅ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
```

### multi-line-summary-first-line (D212)
Avoid docstring summary lines that are not positioned on the first physical line of the docstring.
❌ 
```
def sort_list(l: list[int]) -> list[int]:
    """
    Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the result using the
    bubble sort algorithm.
    """
```
✅ 
```
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the result using the bubble
    sort algorithm.
    """
```

### multi-line-summary-second-line (D213)
Avoid docstring summary lines that are not positioned on the second physical line of the docstring.
❌ 
```
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the result using the
    bubble sort algorithm.
    """
```
✅ 
```
def sort_list(l: list[int]) -> list[int]:
    """
    Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the result using the bubble
    sort algorithm.
    """
```

### new-line-after-last-paragraph (D209)
Avoid multi-line docstrings whose closing quotes are not on their own line.
❌ 
```
def sort_list(l: List[int]) -> List[int]:
    """Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the result using the
    bubble sort algorithm."""
```
✅ 
```
def sort_list(l: List[int]) -> List[int]:
    """Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the result using the bubble
    sort algorithm.
    """
```

### no-blank-line-after-section (D410)
Avoid docstring sections that are not separated by a single blank line.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```

### no-blank-line-before-section (D411)
Avoid docstring sections that are not separated by a blank line.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```

### non-capitalized-section-name (D405)
Avoid section headers in docstrings that do not begin with capital letters.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    args:
        distance: Distance traveled.
        time: Time spent traveling.
    returns:
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    Returns:
…
```

### non-imperative-mood (D401)
Avoid docstring first lines that are not in an imperative mood.
❌ 
```
def average(values: list[float]) -> float:
    """Returns the mean of the given values."""
```
✅ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
```

### over-indentation (D208)
Avoid over-indented docstrings.
❌ 
```
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.
        Sort the list in ascending order and return a copy of the result using the
        bubble sort algorithm.
    """
```
✅ 
```
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the result using the bubble
    sort algorithm.
    """
```

### overindented-section (D214)
Avoid over-indented sections in docstrings.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
        Args:
            distance: Distance traveled.
            time: Time spent traveling.
    Returns:
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    Returns:
…
```

### overindented-section-underline (D215)
Avoid over-indented section underlines in docstrings.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
        ----------
    distance : float
        Distance traveled.
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Parameters
    ----------
    distance : float
        Distance traveled.
…
```

### overload-with-docstring (D418)
Avoid `@overload` function definitions that contain a docstring.
❌ 
```
from typing import overload
@overload
def factorial(n: int) -> int:
    """Return the factorial of n."""
@overload
def factorial(n: float) -> float:
…
```
✅ 
```
from typing import overload
@overload
def factorial(n: int) -> int: ...
@overload
def factorial(n: float) -> float: ...
def factorial(n):
…
```

### signature-in-docstring (D402)
Avoid function docstrings that include the function's signature in the summary line.
❌ 
```
def foo(a, b):
    """foo(a: int, b: int) -> list[int]"""
```
✅ 
```
def foo(a: int, b: int) -> list[int]:
    """Return a list of a and b."""
```

### surrounding-whitespace (D210)
Avoid surrounding whitespace in docstrings.
❌ 
```
def factorial(n: int) -> int:
    """ Return the factorial of n. """
```
✅ 
```
def factorial(n: int) -> int:
    """Return the factorial of n."""
```

### triple-single-quotes (D300)
Avoid docstrings that don't use `"""triple double quotes"""`.
❌ 
```
def kos_root():
    '''Return the pathname of the KOS root directory.'''
def kos_branch():
    'Return the branch name.'
```
✅ 
```
def kos_root():
    """Return the pathname of the KOS root directory."""
def kos_branch():
    """Return the branch name."""
```

### under-indentation (D207)
Avoid under-indented docstrings.
❌ 
```
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.
Sort the list in ascending order and return a copy of the result using the bubble sort
algorithm.
    """
```
✅ 
```
def sort_list(l: list[int]) -> list[int]:
    """Return a sorted copy of the list.
    Sort the list in ascending order and return a copy of the result using the bubble
    sort algorithm.
    """
```

### undocumented-magic-method (D105)
Avoid undocumented magic method definitions.
❌ 
```
class Cat(Animal):
    def __str__(self) -> str:
        return f"Cat: {self.name}"
cat = Cat("Dusty")
print(cat)  # "Cat: Dusty"
```
✅ 
```
class Cat(Animal):
    def __str__(self) -> str:
        """Return a string representation of the cat."""
        return f"Cat: {self.name}"
cat = Cat("Dusty")
print(cat)  # "Cat: Dusty"
```

### undocumented-param (D417)
Avoid function docstrings that do not include documentation for all parameters in the function.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
    Returns:
        Speed as distance divided by time.
…
```
✅ 
```
def calculate_speed(distance: float, time: float) -> float:
    """Calculate speed as distance divided by time.
    Args:
        distance: Distance traveled.
        time: Time spent traveling.
    Returns:
…
```

### undocumented-public-class (D101)
Avoid undocumented public class definitions.
❌ 
```
class Player:
    def __init__(self, name: str, points: int = 0) -> None:
        self.name: str = name
        self.points: int = points
    def add_points(self, points: int) -> None:
        self.points += points
```

### undocumented-public-function (D103)
Avoid undocumented public function definitions.
❌ 
```
def calculate_speed(distance: float, time: float) -> float:
    try:
        return distance / time
    except ZeroDivisionError as exc:
        raise FasterThanLightError from exc
```

### undocumented-public-init (D107)
Avoid public `__init__` method definitions that are missing docstrings.
❌ 
```
class City:
    def __init__(self, name: str, population: int) -> None:
        self.name: str = name
        self.population: int = population
```
✅ 
```
class City:
    def __init__(self, name: str, population: int) -> None:
        """Initialize a city with a name and population."""
        self.name: str = name
        self.population: int = population
```

### undocumented-public-method (D102)
Avoid undocumented public method definitions.
❌ 
```
class Cat(Animal):
    def greet(self, happy: bool = True):
        if happy:
            print("Meow!")
        else:
            raise ValueError("Tried to greet an unhappy cat.")
```

### undocumented-public-module (D100)
Avoid undocumented public module definitions.
❌ 
```
class FasterThanLightError(ZeroDivisionError): ...
def calculate_speed(distance: float, time: float) -> float: ...
```
✅ 
```
"""Utility functions and classes for calculating speed.
This module provides:
- FasterThanLightError: exception when FTL speed is calculated;
- calculate_speed: calculate speed given distance and time.
"""
class FasterThanLightError(ZeroDivisionError): ...
…
```

### undocumented-public-nested-class (D106)
Avoid undocumented public class definitions, for nested classes.
❌ 
```
class Foo:
    """Class Foo."""
    class Bar: ...
bar = Foo.Bar()
bar.__doc__  # None
```
✅ 
```
class Foo:
    """Class Foo."""
    class Bar:
        """Class Bar."""
bar = Foo.Bar()
bar.__doc__  # "Class Bar."
```

### undocumented-public-package (D104)
Avoid undocumented public package definitions.
❌ `__all__ = ["Player", "Game"]`
✅ 
```
"""Game and player management package.
This package provides classes for managing players and games.
"""
__all__ = ["player", "game"]
```

### unnecessary-multiline-docstring (D200)
Avoid single-line docstrings that are broken across multiple lines.
❌ 
```
def average(values: list[float]) -> float:
    """
    Return the mean of the given values.
    """
```
✅ 
```
def average(values: list[float]) -> float:
    """Return the mean of the given values."""
```
