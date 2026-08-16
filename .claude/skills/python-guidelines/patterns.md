# Python Patterns

> Distilled from **python-patterns.guide — A Guide to Python's Design Patterns**
> by Brandon Rhodes.
> Source: <https://python-patterns.guide/>
> Concatenated with attribution; each pattern retains its canonical URL.

Every pattern below is a reusable design decision. Each entry starts with a
**Verdict** summarizing whether the pattern is Pythonic (use it), a non-Python
carryover (prefer an alternative), or worth knowing for porting code. The
sections follow the order:

1. **Python-specific patterns** (module globals, sentinel objects, prebound methods)
2. **Gang of Four patterns** adapted to Python (creational → structural → behavioral)
3. **Composition over inheritance** (the most important meta-pattern)
4. **Fowler refactoring patterns** (overview)

Prefer the Python-specific patterns over translating OOP-heavy idioms from
Java/C++. When a GoF pattern has a more idiomatic Python approach, the verdict
will say so.

---

<!-- source: https://python-patterns.guide/python/module-globals/ -->

Verdict

Like several other scripting languages, Python parses the outer level of each module as normal code. Un-indented assignment statements, expressions, and even loops and conditionals will execute as the module is imported. This presents an excellent opportunity to supplement a module’s classes and functions with constants and data structures that callers will find useful — but also offers dangerous temptations: mutable global objects can wind up coupling distant code, and I/O operations impose import-time expense and side effects.

Every Python module is a separate namespace. A module like `json` can offer a `loads()` function without conflicting with, replacing, or overwriting the completely different `loads()` function defined over in the `pickle` module.

Separate namespaces are crucial to making a programming language tractable. If Python modules were not separate namespaces, you would be unable to read or write Python code by keeping your attention focused on the module in front of you — a line of code might use, or accidentally conflict with, a name defined anywhere else in the Standard Library or a third-party module you have installed. Upgrading a third-party module could break your entire program if the new version defined a new global that conflicted with yours. Programmers who are forced to code in a language without namespaces soon find themselves festooning global names with prefixes, suffixes, and extra punctuation in a desperate race to keep them from conflicting.

While every function and class is, of course, an object — in Python, everything is an object — the Module Global pattern more specifically refers to normal object instances that are given names at the global level of a module.

Two patterns use Module Globals but are important enough to warrant their own articles:

*   [Prebound Methods](https://python-patterns.guide/python/prebound-methods/) are generated when a module builds an object and then assigns one or more of the object’s bound methods to names at the module’s global level. The names can be used to call the methods later without needing to find the object itself.

*   While a [Sentinel Object](https://python-patterns.guide/python/sentinel-object/) doesn’t have to live in a module’s global namespace — some sentinel objects are defined as class attributes, while others are private and live inside of a closure — many sentinels, both in the Standard Library and beyond, are defined and accessed as module globals.

This article will cover some other common cases.

## The Constant Pattern[¶](https://python-patterns.guide/python/module-globals/#the-constant-pattern "Link to this heading")

Modules often assign useful numbers, strings, and other values to names in their global scope. The Standard Library includes many such assignments, from which we can excerpt a few examples.

January = 1                   # calendar.py
WARNING = 30                  # logging.py
MAX_INTERPOLATION_DEPTH = 10  # configparser.py
SSL_HANDSHAKE_TIMEOUT = 60.0  # asyncio.constants.py
TICK = "'"                    # email.utils.py
CRLF = "\r\n"                 # smtplib.py

Remember that these are “constants” only in the sense that the objects themselves are immutable. The names can still be reassigned.

import calendar
calendar.January = 13
print(calendar.January)

13

Or deleted, for that matter.

del calendar.January
print(calendar.January)

Traceback (most recent call last):
  ...
AttributeError: module 'calendar' has no attribute 'January'

In addition to integers, floats, and strings, constants also include immutable containers like tuples and frozen sets:

all_errors = (Error, OSError, EOFError)  # ftplib.py
bytes_types = (bytes, bytearray)         # pickle.py
DIGITS = frozenset("0123456789")         # sre_parse.py

More specialized immutable data types also serve as constants:

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)  # datetime

On rare occasions, a module global which the code clearly never intends to modify uses a mutable data structure anyway. Plain mutable sets are common in code that pre-dates the invention of the `frozenset`. Dictionaries are still used today because, alas, the Standard Library doesn’t offer a frozen dictionary.

# socket.py
_blocking_errnos = { EAGAIN, EWOULDBLOCK }

# locale.py
windows_locale = {
  0x0436: "af_ZA", # Afrikaans
  0x041c: "sq_AL", # Albanian
  0x0484: "gsw_FR",# Alsatian - France
  ...
  0x0435: "zu_ZA", # Zulu
}

Constants are often introduced as a refactoring: the programmer notices that the same value `60.0` is appearing repeatedly in their code, and so introduces a constant `SSL_HANDSHAKE_TIMEOUT` for the value instead. Each use of the name will now incur the slight cost of a search into the global scope, but this is balanced by a couple of advantages. The constant’s name now documents the value’s meaning, improving the code’s readability. And the constant’s assignment statement now provides a single location where the value can be edited in the future without needing to hunt through the code for each place `60.0` was used.

These advantages are weighty enough that a constant is sometimes introduced even for a value that’s used only once, hoisting a literal that was hidden deep in the code up into visibility as a global.

Some programmers place constant assignments close to the code that use them; others put all constants at the top of the file. Unless a constant is placed so close to its code that it will always be in view of human readers, it can be more friendly to put constants at the top of the module for the easy reference of readers who haven’t yet configured their editors to support jump-to-definition.

Another kind of constant is not directed inwards, towards the code in the module itself, but outwards as part of the module’s advertised API. A constant like `WARNING` from the `logging` module offers the advantages of a constant to the caller: code will be more readable, and the constant’s value could be adjusted later without every caller needing to edit their code.

You might expect that a constant intended for the module’s own use, but not intended for callers, would always start with an underscore to mark it private. But Python programmers are not consistent in marking constants private, perhaps because the cost of needing to keep a constant around forever because a caller might have decided to start using it is smaller than the cost of having a helper function or class’s API forever locked up.

## Import-time computation[¶](https://python-patterns.guide/python/module-globals/#import-time-computation "Link to this heading")

Sometimes constants are introduced for efficiency, to avoid recomputing a value every time code is called. For example, even though math operations involving literal numbers are in fact optimized away in all modern Python implementations, developers often still feel more comfortable making it explicit that the math should be done at import time by assigning the result to a module global:

# zipfile.py
ZIP_FILECOUNT_LIMIT = (1 << 16) - 1

When the math expression is complicated, assigning a name also enhances the code’s readability.

As another example, there exist special floating point values that cannot be written in Python as literals; they can only be generated by passing a string to the float type. To avoid calling `float()` with `'nan'` or `'inf'` every single time such a value is needed, modules often build such values only once as module globals.

# encoder.py
INFINITY = float('inf')

A constant can also capture the result of a conditional to avoid re-evaluating it each time the value is needed — as long, of course, as the condition won’t be changing while the program is running.

# shutil.py
COPY_BUFSIZE = 1024 * 1024 if _WINDOWS else 16 * 1024

My favorite example of computed constants in the Standard Library is the `types` module. I had always assumed it was implemented in C, to gain special access to built-in type objects like `FunctionType` and `LambdaType` that are defined by the language implementation itself.

It turns out? I was wrong. The `types` module is written in plain Python!

Without any special access to language internals, it does what anyone else would do to learn what type functions have. It creates a function, then asks its type:

# types.py
def _f(): pass
FunctionType = type(_f)

On the one hand, this makes the `types` module seem almost superfluous — you could always use the same trick to discover `FunctionType` yourself. But on the other hand, importing it from `types` lets both major benefits of the Constant Pattern shine: code becomes more readable because `FunctionType` will have the same name everywhere, and more efficient because the constant only needs to be computed once no matter how many modules in a large system might use it.

## Dunder Constants[¶](https://python-patterns.guide/python/module-globals/#dunder-constants "Link to this heading")

A special case of constants defined at a module’s global level are “dunder” constants whose names start and end with double underscores.

Several Module Global dunder constants are set by the language itself. For the official list, look for the “Modules” subheading in the Python Reference’s section on [the standard type hierarchy](https://docs.python.org/3/reference/datamodel.html#the-standard-type-hierarchy). The two encountered most often are `__name__`, which programs need to check because of Python’s awful design decision to assign the fake name `'__main__'` to the module invoked from the command line, and `__file__`, the full filesystem path to the module’s Python file itself — which is almost universally used to find data files included in a package, even though the official recommendation these days is to use [`pkgutil.get_data()`](https://docs.python.org/3/library/pkgutil.html#pkgutil.get_data) instead.

here = os.path.dirname( __file__ )

Beyond the dunder constants set by the language runtime, there is one Python recognizes if a module chooses to set it: if `__all__` is assigned a sequence of identifiers, then only those names will be imported into another module that does `from … import *`. You might have expected `__all__` to become less popular as `import *` gained a reputation as an anti-pattern, but it has gained a happy second career limiting the list of symbols included by automatic documentation engines like [Sphinx autodoc module](http://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html).

Even though most modules never plan to modify `__all__`, they inexplicably specify it as a Python list. It is more elegant to use a tuple.

Beyond these official dunder constants, some modules add even more. Assignments to names like `__author__` and `__version__` are scattered across the Standard Library and beyond. Tools tend to ignore these non-standard names, but a human reader might occasionally find them informative.

Beware that there does not seem to be agreement, even within the Standard Library, about what type `__author__` should have.

# bz2.py
 __author__  = "Nadeem Vawda <nadeem.vawda@gmail.com>"

# inspect.py
 __author__  = ('Ka-Ping Yee <ping@lfw.org>',
              'Yury Selivanov <yselivanov@sprymix.com>')

Why not `author` and `version` instead, without the dunders? An early reader probably misunderstood dunders, which really meant “special to the Python language runtime,” as a vague indication that a value was module metadata rather than module code. A few Standard Library modules do offer their version without dunders, but without even agreeing on the capitalization.

VERSION = "1.3.0"  # etree/ElementTree.py
version = "0.20"   # sax/expatreader.py
version = "0.9.0"  # tarfile.py

To avoid the inconsistencies surrounding these informal and ad-hoc metadata conventions, a package that expects to be installed with `pip` can learn the names and versions of other installed packages directly from the Python package installation system. More information is available in the [setuptools documentation on the `pkg_resources` module](https://setuptools.readthedocs.io/en/latest/pkg_resources.html).

## The Global Object Pattern[¶](https://python-patterns.guide/python/module-globals/#id1 "Link to this heading")

In the full-fledged Global Object pattern, as in the Constant pattern, a module instantiates an object at import time and assigns it a name in the module’s global scope. But the object does not simply serve as data; it is not merely an integer, string, or data structure. Instead, the object is made available for the sake of the methods it offers — for the actions it can perform.

The simplest Global Objects are immutable. A common example is a compiled regular expression — here are a few examples from the Standard Library:

escapesre = re.compile(r'[\\"]')       # email/utils.py
magic_check = re.compile('([*?[])')    # glob.py
commentclose = re.compile(r'--\s*>')   # html/parser.py
HAS_UTF8 = re.compile(b'[\x80-\xff]')  # json/encoder.py

Compiling a regular expression as a module global is a good example of the more general Global Object pattern. It achieves an elegant and safe transfer of expense from later in a program’s runtime to import time instead. The tradeoffs are:

*   The cost of importing the module increases by the cost of compiling the regular expression (plus the tiny cost of assigning it to a global name).

*   The import-time cost is now borne by every program that imports the module. Even if a program doesn’t happen to call any code that uses the `HAS_UTF8` regular expression shown above, it will incur the expense of compiling it whenever it imports the `json` module. (Plot twist: in Python 3, the pattern is no longer even used in the module! But its name was not marked private with a leading underscore, so I suppose it’s not safe to remove — and every `import json` gets to pay its cost forever?)

*   But functions and methods that do, in fact, need to use the regular expression will no longer incur a repeated cost for its compilation. The compiled regular expression is ready to start scanning a string immediately! If the regular expression is used frequently, like in the inner loop of a costly operation like parsing, the savings can be considerable.

*   The global name will make calling code more readable than if the regular expression, when used locally, is used anonymously in a larger expression. (If readability is the only concern, though, remember that you can define the regular expression’s string as a global but skip the cost of compiling it at module level.)

This list of tradeoffs is about the same, by the way, if you move a regular expression out into a class attribute instead of moving it all the way out to the global scope. When I finally get around to writing about Python and classes, I’ll link from here to further thoughts on class attributes.

## Global Objects that are mutable[¶](https://python-patterns.guide/python/module-globals/#global-objects-that-are-mutable "Link to this heading")

But what about Global Objects that are mutable?

They are easiest to justify when they wrap system resources that are by their nature also global to an operating system process. One example in the Standard Library itself is the `environ`[object](https://docs.python.org/3/library/os.html#os.environ) that gives your Python program the “environment” — the text keys and values supplying your timezone, terminal type, so forth — that was passed to your Python program from its parent process.

Now, it is arguable whether your program should really be writing new values into its environment as it runs. If you’re launching a subprocess that needs an environment variable adjusted, the `subprocess` routines offer an `env` parameter. But if code does need to manipulate this global resource, then it makes sense for that access to be mediated by a correspondingly global Python object:

# os.py
environ = _createenviron()

Through this global object, the various routines, and perhaps threads, in a Python program coordinate their access to this process-wide resource. Any change:

import os
os.environ['TERM'] = 'xterm'

— will be immediately visible to any other part of the program that reads that environment key:

>>> os.environ['TERM']
'xterm'

The problems with coupling distant parts of your codebase, and even unrelated parts of different libraries, through a unique global object are well known.

*   Tests that were previously independent are suddenly coupled through the global object and can no longer safely be run in parallel. If one test makes a temporary assignment to `environ['PATH']` just before another test launches a binary with `subprocess`, the binary will inherit the test value of `$PATH` — possibly causing an error.

*   You can sometimes serialize access to a global object through a lock. But unless you do a thorough audit of all of the libraries your code uses, and continue to audit them when upgrading to new versions, it can be difficult to even know which tests call code that ultimately touches particular global object like `environ`.

*   Even tests run serially, not in parallel, will now wind up coupled if one test fails to restore `environ` to its original state before the next test runs. This can, it’s true, be mitigated with teardown routines or with mocks that automatically restore state. But unless every single test is perfectly cautious, your test suite can still suffer from exceptions that depend on random test ordering or on whether a previous test succeeded or exited early.

*   These dangers beset not only tests but production runs as well. Even if your application doesn’t launch multiple threads, there can be surprising cases where a refactoring winds up calling code that performs one operation on `environ` right in the middle of another routine that was also in the middle of transforming its state.

The Standard Library has more examples of the Mutable Global pattern — both public globals and private ones litter its modules. Some correspond to unique resources at the system level:

# Lib/multiprocessing/process.py
_current_process = _MainProcess()
_process_counter = itertools.count(1)

Others correspond to no outside resource but instead serve as single points of coordination for a process-wide activity like logging:

# Lib/logging/__init__.py
root = RootLogger(WARNING)

Third-party libraries can supply dozens of more examples, from global HTTP thread pools and database connections to registries of request handlers, library plugins, and third-party codecs. But in every case, the Mutable Global courts all of the dangers listed above in return for the convenience of putting a resource where every module can reach it.

My advice, to the extent that you can, is to write code that accepts arguments and returns values computed from them. Failing that, try passing database connections or open sockets to code that will need to interact with the outside world. It is a compromise for code that finds itself stranded from the resources it needs to resort to accessing a global.

The glory of Python, of course, is that it usually makes even anti-patterns and compromises read fairly elegantly in code. An assignment statement at the global level of a module is as easy to write and read as any other assignment statement, and callers can access the Mutable Global through exactly the same import statement they use for functions and classes.

## Import-time I/O[¶](https://python-patterns.guide/python/module-globals/#import-time-i-o "Link to this heading")

Many of the worst Global Objects are those that perform file or network I/O at import time. They not only impose the cost of that I/O on every library, script, and test that need the module, but expose them to failure if a file or network is not available.

Library authors have an unfortunate tendency to make assumptions like “the file `/etc/hosts` will always exist” when, in fact, they can’t know ahead of time all the exotic environments their code will one day face — maybe a tiny embedded system that in fact lacks that file; maybe a continuous integration environment spinning up containers that lack any network configuration at all.

Even when faced with this possibility, a module author might still try to defend their import-time I/O: “But delaying the I/O until after import time simply postpones the inevitable — if the system doesn’t have `/etc/hosts` then the user will get exactly the same exception later anyway.” The attempt to make this excuse reveals three misunderstandings:

1.   Errors at import time are far more serious than errors at runtime. Remember that at the moment your package is imported, the program’s main routine has probably not started running — the caller is usually still up in the middle of the stack of `import` statements at the top of their file. They have probably not yet set up logging and have not yet entered their application’s main `try…except` block that catches and reports failures, so any errors during import will probably print directly to the standard output instead of getting properly reported.

2.   Applications are often written to survive the failure of some operations so that in an emergency they can still perform other functions. Even if features that need your library will now hit an exception, the application might have many others it can continue to offer — or could, if you didn’t kill it with an exception at import time.

3.   Finally, library authors need to keep in mind that a Python program that imports their library might not even use it! Never assume that simply because your code has been imported, it will be used. There are many situations where a module gets imported incidentally, as the dependency of yet further modules, but never happens to get called. By performing I/O at import time, you could impose expense and risk on hundreds of programs and tests that don’t even need or care about your network port, connection pool, or open file.

For all of these reasons, it’s best for your global objects to wait until they’re first called before opening files and creating sockets — because it’s at the moment of that first call that the library knows the main program is now up and running, and knows that its services are in fact definitely needed in this particular run of the program.

I’ll admit that, when my package needs to load a small data file that’s embedded in the package itself, I do sometimes break this rule.

---

<!-- source: https://python-patterns.guide/python/sentinel-object/ -->

_A Python variation on the traditional Sentinel Value pattern_

Verdict

The Sentinel Object pattern is a standard Pythonic approach that’s used both in the Standard Library and beyond. The pattern most often uses Python’s built-in `None` object, but in situations where `None` might be a useful value, a unique sentinel `object()` can be used instead to indicate missing or unspecified data.

Contents:

*   [The Sentinel Object Pattern](https://python-patterns.guide/python/sentinel-object/#the-sentinel-object-pattern)

    *   [Sentinel Value](https://python-patterns.guide/python/sentinel-object/#sentinel-value)

    *   [The Null Pointer Pattern](https://python-patterns.guide/python/sentinel-object/#the-null-pointer-pattern)

    *   [The Null Object Pattern](https://python-patterns.guide/python/sentinel-object/#the-null-object-pattern)

    *   [Sentinel Objects](https://python-patterns.guide/python/sentinel-object/#sentinel-objects)

Programming is easiest in problem domains where values are always specified: where everyone in the database is guaranteed to have a name, where we know the age of every employee, and where a datum was collected successfully for every second of the experiment.

But the world is rarely that simple, and so patterns are needed for those cases where object attributes or whole objects go missing. What simple mechanisms are available to distinguish useful data from placeholders that indicate data is absent?

## Sentinel Value[¶](https://python-patterns.guide/python/sentinel-object/#sentinel-value "Link to this heading")

The traditional Sentinel Value pattern will be familiar to Python programmers from the [`str.find()`](https://docs.python.org/3/library/stdtypes.html#str.find) method. While its alternative [`str.index()`](https://docs.python.org/3/library/stdtypes.html#str.index) is more rigorous, raising an exception if it can’t find the substring you’re asking about, `find()` lets you skip writing an exception handler for a missing substring by returning the sentinel value `-1` when the substring is not found. This often saves a line of code and a bit of indentation:

try:
    i = a.index(b)
except:
    return

# versus

i = a.find(b)
if i == -1:
    return

This is a classic example of a sentinel value. The value `-1` is simply an integer, just like the function’s other possible return values, but with a special meaning that has been agreed upon ahead of time— and woe betide the program that is returned `-1`, forgets to check, and tries using it as an index into the string! The result will not be what the programmer intended.

If [`str.find()`](https://docs.python.org/3/library/stdtypes.html#str.find) had been invented today, it would instead have used the Sentinel Object pattern that we will describe below by simply returning `None` for “not found”. That would have left no possibility of the return value being used accidentally as an index.

Sentinel values are particularly common today in the Go language, whose design encourages a programming style that always returns strings instead of mere references to them — forcing the programmer to choose some particular string, like the empty string or a special unique sentinel, to indicate that no data was collected or is present.

In Python, the Django framework is famous for contradicting several decades of database practice by recommending that you “[Avoid using null on string-based fields](https://docs.djangoproject.com/en/dev/ref/models/fields/#null)” — with the frequent result that, as in Go, code becomes simpler; checks for the empty string replace checks for `None`; and the program no longer crashes when later code tries invoking a string method on what turns out to be `None`.

## The Null Pointer Pattern[¶](https://python-patterns.guide/python/sentinel-object/#the-null-pointer-pattern "Link to this heading")

The null pointer pattern is impossible in Python, but worth mentioning to outline the difference between Python and languages that complicate their data model with `nil` or `NULL` pointers.

Every name in Python either does not exist, or exists and refers to an object. You can remove a name with `del name`, or else you can assign a new object to it; Python offers no other alternatives. Behind the scenes, each name in Python is a pointer that stores the address of the object to which it currently refers. Even if the name points to an object as simple as the `None` object, it will contain a valid address.

This guarantee supports an interesting sentinel pattern down in the default C language implementation of Python. The C language lacks Python’s guarantee that a name — which C calls a “pointer” — will always hold the address of a valid object. Taking advantage of this flexibility, C programmers use an address of zero to mean “this pointer currently doesn’t point at anything” — which makes zero, or `NULL` as many C programs define it, a sentinel value. Pointers which might be `NULL` need to be checked before being used, or the program will die with a `segmentation fault`.

The fact that all Python values, even `None` and `False`, are real objects with non-zero addresses means that Python functions implemented in C have the value `NULL` available to mean something special: a `NULL` pointer means “this function did _not_ complete and return a value; instead, it raised an exception.” This allows the C code beneath Python to avoid the two-value return pattern that pervades Go code:

# Go needs to separately represent “the return value”
# and “did this die with an error.”

byte_count, err := fmt.Print("Hello, world!")
if err != nil {
        ...
}

Instead, C language routines that call Python can distinguish legitimate return values from an exception using only the single return value supported by C functions:

# The pointer to a Python object instead means
# “an exception was raised” if its value is NULL.

PyObject *my_repr = PyObject_Repr(obj);
if (my_repr == NULL) {
     ...
}

The exception itself is stored elsewhere and can be retrieved using the Python C API.

## The Null Object Pattern[¶](https://python-patterns.guide/python/sentinel-object/#the-null-object-pattern "Link to this heading")

“Null objects” are real, valid objects that happen to represent a blank value or an item that does not exist. My attention was drawn to this pattern while reading the book [Refactoring by Martin Fowler](https://python-patterns.guide/fowler-refactoring/) which credits Bobby Woolf for its explication. Note that this pattern has nothing to do with the “null pointer” explained in the previous section! Instead it describes a special kind of sentinel object.

Imagine a sequence of `Employee` objects which usually have another employee as their `manager` attribute but not always. The default Pythonic approach to represent “no manager” would be to assign `None` to the attribute.

A routine tasked with displaying an employee profile will have to check for the sentinel object `None` before trying to invoke any methods on the manager:

for e in employees:
    if e.manager is None:
        m = 'no one'
    else:
        m = e.manager.display_name()
    print(e.name, '-', m)

And this pattern will need to be repeated everywhere that code touches the manager attribute.

Woolf offers the intriguing alternative of replacing all of the `None` manager values with an object specifically designed to represent the idea of “no one”:

NO_MANAGER = Person(name='no acting manager')

Employee objects will now be assigned this `NO_MANAGER` object instead of `None`, and both kinds of code touching employee managers will benefit:

*   Code that produces simple displays or summaries can simply print or tally the `NO_MANAGER` manager object as though it were a normal employee object. When code can run successfully against the Null Object, the need for a special `if` statement disappears.

*   Code that does need to specially handle the case of an employee with no acting manager now becomes a bit more readable. Instead of using the generic `is None` it will perform the check with the specific `is NO_MANAGER` and will thereby gain a bit more readability.

While not appropriate in all situations — it can, for example, be difficult to design Null Objects that keep averages and other statistics valid — Null Objects appear even in the Python Standard Library: the `logging` module has a `NullHandler` which is a drop-in replacement for its other handlers but does no actual logging.

## Sentinel Objects[¶](https://python-patterns.guide/python/sentinel-object/#sentinel-objects "Link to this heading")

Finally we come to the Sentinel Object pattern itself.

The standard Python sentinel is the built-in `None` object, used wherever some alternative needs to be provided to an integer, float, string, or other meaningful value. For most programs it is entirely sufficient, and its presence can be infallibly tested with:

if other_object is None:
    ...

But there are two interesting circumstances where programs need an alternative to `None`.

First, a general purpose data store doesn’t have the option of using `None` for missing data if users might themselves try to store the `None` object.

As an example, the Python Standard Library’s `functools.lru_cache()` uses the Sentinel Object pattern internally. Hidden inside of a closure is an utterly unique object that it creates separately for each separate instance of the cache:

sentinel = object()  # unique object used to signal cache misses

By providing this sentinel object as the second argument to `dict.get()` — here aliased to the name `cache_get` in a closure-level private example of the [Prebound Methods](https://python-patterns.guide/python/prebound-methods/) pattern — the cache can distinguish a function call whose result is already cached and happened to be `None` from a function call that has not yet been cached:

result = cache_get(key, sentinel)
if result is not sentinel:
    ...

This pattern occurs several times in the Standard Library.

*   As shown above, `functools.lru_cache()` uses a sentinel object internally.

*   The `bz2` module has a global `_sentinel` object.

*   The `configparser` module has a sentinal `_UNSET` also defined as a module global.

The second interesting circumstance that calls for a sentinel is when a function or method wants to know whether a caller supplied an optional keyword argument or not. Usually Python programmers give such an argument a default of `None`. But if your code truly needs to know the difference, then a sentinel object will allow you to detect it.

An early description of using sentinels for parameter defaults was Fredrik Lundh’s [“Default Parameter Values in Python”](http://effbot.org/zone/default-values.htm) which over the years was followed by posts from Ian Bicking [“The Magic Sentinel”](http://www.ianbicking.org/blog/2008/12/the-magic-sentinel.html) and Flavio Curella [“Sentinel values in Python”](https://www.revsys.com/tidbits/sentinel-values-python/) who both worried about their sentinel objects’ lack of a readable `repr()` and came up with various fixes.

But whatever the application, the core of the Sentinel Object pattern is that it is the object’s identity — _not_ its value — that lets the surrounding code recognize its significance. If you are using an equality operator to detect the sentinel, then you are merely using the Sentinel Value pattern described at the top of this page. The Sentinel Object is defined by its use of the Python `is` operator to detect whether the sentinel is present.

---

<!-- source: https://python-patterns.guide/python/prebound-methods/ -->

_A pattern native to the Python language._

Verdict

A powerful technique for offering callables at the top level of your module that share state through a common object.

There are occasions on which a Python module wants to offer several routines in the module’s global namespace that will need to share state with each other at runtime.

Probably the most famous example is the Python Standard Library’s [`random`](https://docs.python.org/3/library/random.html) module. While it does provide advanced users with the option to build their own `Random` instance, most programmers opt for the convenient slate of routines available in the module’s global namespace — like [randrange()](https://docs.python.org/3/library/random.html#random.randrange), [randint()](https://docs.python.org/3/library/random.html#random.randint), and [choice()](https://docs.python.org/3/library/random.html#random.choice) — that mirror the methods of a `Random` object.

How do these top-level routines share state?

Behind the scenes these callables are, in fact, methods that have all been bound ahead of time to a single instance of `Random` that the module itself has gone ahead and constructed.

After reviewing the problem that the Prebound Methods pattern solves, we will see how the pattern looks in Python code.

## Alternatives[¶](https://python-patterns.guide/python/prebound-methods/#alternatives "Link to this heading")

The most primitive approach to sharing state between a pair of module-level callables is to write a pair of functions that manipulate global data that’s stored next to them at the top level of the module.

Imagine that we want to offer a simple random number generator. It returns, in an endless loop, the numbers 1 through 255 in a fixed pseudo-random order. We also want to offer a simple `set_seed()` routine that resets the state of the generator to a known value — which is important both for tests that use random numbers, and for simulations driven by pseudo-randomness that want to offer reproducible results.

If Python only supported plain functions, we might store the shared seed as a module global that our functions would directly access and modify:

from datetime import datetime

_seed = datetime.now().microsecond % 255 + 1

def set_seed(value):
    global _seed
    _seed = value

def random():
    global _seed
    _seed, carry = divmod(_seed, 2)
    if carry:
        _seed ^= 0xb8
    return _seed

There are several problems with this approach.

First, it is impossible to ever instantiate a second copy of this random number generator. If two threads each wanted their own generator to avoid needing to protect it with locks, then they would be out of luck.

(Okay, not really; this is Python. Think of the possibilities! You could import the module, save a reference to it, remove it from the `sys.modules` dictionary, and then import it again to get a second copy. Or you could manually instantiate a second module object and copy all three names across. By “out of luck” I refer only to sane Pythonic approaches.)

Second, it is more difficult to decouple your random number generator tests from each other if the generator’s state is global. Instead of each test getting to create and exercise a separate isolated instance, the tests will all have to share the single generator and correctly reset its state before the next test runs.

Third, this approach abandons encapsulation. This will sound like a fuzzier complaint than the previous two, but it can detract from readability (“readability counts”) for a small tight system of two functions and a `seed` to be splayed out as three separate and not obviously related names in a module which might contain dozens of other objects.

To solve the above problems, we indent the two functions and wrap them up as methods of a new Python class. The two methods and their state can then be happily bundled together:

from datetime import datetime

class Random8(object):
    def  __init__ (self):
        self.set_seed(datetime.now().microsecond % 255 + 1)

    def set_seed(self, value):
        self.seed = value

    def random(self):
        self.seed, carry = divmod(self.seed, 2)
        if carry:
            self.seed ^= 0xb8
        return self.seed

This imposes an extra step on the caller: the object will have to be instantiated before the two methods can be called. Is there a way to let the caller skip that step?

The software engineer would do well to stop for a moment and to think quite seriously about the fact that in the vast majority of cases simply defining a class like this is enough. It will take only a single statement for your user to create an instance of your class. If their own application’s architecture is too deeply compromised for them to easily pass the instance everywhere it’s needed, they can always store the instance as a module global in one of their own modules for the use of the rest of their code.

There are several reasons that that the Prebound Methods pattern is a particularly good fit for a random number generator:

1.   Instantiating a random number generator requires a system call — in our case, asking for the date; for the Python `random` module, fetching bytes from the system entropy pool. If every module needing a random number had to instantiate its own `Random` object, then this cost would be incurred repeatedly.

2.   Pseudo-random number generators are an interesting case of a resource whose behavior can be even more desirable when shared. If you are the lone caller to an instance, you see its completely predictable repeating sequence of values. If instead you are sharing that instance with other code, the generator will appear to skip ahead in its sequence unpredictably each time other callers have themselves called the generator.

3.   Since most users of `random`, including several modules within the Standard Library, import it specifically to use its module-level calls, it is rare for the pre-built `Random` instance that powers them to languish unused.

If the costs and benefits strike a similar balance for a module of your own you are designing, then the Prebound Method pattern can let you deliver remarkable convenience.

## The pattern[¶](https://python-patterns.guide/python/prebound-methods/#the-pattern "Link to this heading")

To offer your users a slate of Prebound Methods:

*   Instantiate your class at the top level of your module.

*   Consider assigning it a private name prefixed with an underscore `_` that does not invite users to meddle with the object directly.

*   Finally, assign a bound copy of each of the object’s methods to the module’s global namespace.

For the random number generator that we used as an illustration above, the entire module might look like this:

from datetime import datetime

class Random8(object):
    def  __init__ (self):
        self.set_seed(datetime.now().microsecond % 255 + 1)

    def set_seed(self, value):
        self.seed = value

    def random(self):
        self.seed, carry = divmod(self.seed, 2)
        if carry:
            self.seed ^= 0xb8
        return self.seed

_instance = Random8()

random = _instance.random
set_seed = _instance.set_seed

Users will now be able to invoke each method as though it were a stand-alone function. But the methods will secretly share state thanks to the common instance that they are bound to, without requiring the user to manage or pass that state explicitly.

When exercising this pattern, please be responsible about the dangers of instantiating an object at import time. This pattern is usually not appropriate for a class whose constructor creates files, reads a database configuration, opens sockets, or that in general will inflict side effects on the program importing them. In that case, you will do better to either avoid the Prebound Methods pattern entirely, or else to defer any actual side effects until one of the methods is called. You could choose a middle ground of providing a `setup()` method and requiring application programmers to invoke it before they can expect any of the other routines to work.

But for lightweight objects that can be instantiated without substantial delay or complication, the Prebound Methods pattern is an elegant way to make the stateful behavior of a class instance available up at a module’s global level.

Examples of the pattern are strewn merrily across the Standard Library even beyond the `random` module we used as our example. The `calendar.py` module uses it:

c = TextCalendar()

...

monthcalendar = c.monthdayscalendar
prweek = c.prweek
week = c.formatweek
weekheader = c.formatweekheader
prmonth = c.prmonth
month = c.formatmonth
calendar = c.formatyear
prcal = c.pryear

As does the venerable old `reprlib.py`, to offer a single `repr()` routine:

aRepr = Repr()
repr = aRepr.repr

As do several other modules — you will find the Prebound Methods pattern used with each of these Standard Library objects:

*   `distutils.log._global_log`

*   `multiprocessing.forkserver._forkserver`

*   `multiprocessing.semaphore_tracker._semaphore_tracker`

*   `secrets._sysrand`

One final hint: it is almost always better to assign methods to global names explicitly. Even if there are a dozen methods, I recommend going ahead and writing a quick stack of a dozen assignment statements aligned at the left-hand column of your module that make visible the whole list of global names you are defining. The fact that Python is a dynamic language might tempt you to automate the series of assignments instead, using attribute introspection and a `for` loop. I advise against it. Python programmers believe that “Explicit is better than implicit” — and materializing the stack of names as real code will better support human readers, language servers, and even venerable old `grep`.

---

<!-- source: https://python-patterns.guide/gang-of-four/ -->

It can be hard to remember, but object oriented programming was all the rage back in the roaring 1990s. Instead of talking about the power of first-class functions and general-purpose data structures, many programmers were festooning their code with virtual methods, superclasses, subclasses, and clever mixins. Programmers often found that language limitations and static types were locking them out of improvements they later wanted to make to their code.

The “Gang of Four” rode to the rescue. Their book’s first and most fundamental pattern, blazoned across the page in italics, would — if practiced consistently — break programmers free of code that was hard-wired to concrete classes:

> _“Program to an interface, not an implementation.”_

At the expense of more code, this practice moved programmers one step towards the freedom we enjoy in a dynamic language like Python. Each of the book’s further chapters tackled a different design conundrum posed by the era’s limited programming languages and solved it. Most of the solutions introduced new classes to cleverly decouple code that would otherwise be too tightly linked.

This site examines the old patterns from the Gang of Four in the context of a modern dynamic programming language in which classes and functions are first-class objects, to see which patterns are still useful and which ones disappear. You can start working through the patterns back on this site’s [front page](https://python-patterns.guide/).

---

<!-- source: https://python-patterns.guide/gang-of-four/abstract-factory/ -->

_A “Creational Pattern” from the_[Gang of Four book](https://python-patterns.guide/gang-of-four/)

Verdict

The Abstract Factory is an awkward workaround for the lack of first-class functions and classes in less powerful programming languages. It is a poor fit for Python, where we can instead simply pass a class or a factory function when a library needs to create objects on our behalf.

The Python Standard Library’s `json` module is a good example of a library that needs to instantiate objects on behalf of its caller. Consider a JSON string like this one:

text = '{"total": 9.61, "items": ["Americano", "Omelet"]}'

By default, the `json` module’s `loads()` function will create `unicode` objects for the strings `"Americano"` and `"Omelet"`, a `list` to hold them, a Python `float` for `9.61`, and a `dict` with `unicode` keys for the top-level JSON object.

But some users will not be content with these defaults. For example, an accountant would probably be unhappy with the choice of a `float` to represent an exact amount like “9 dollars 61 cents” and would prefer an exact `Decimal` instead.

The need to control what kind of numeric object the `json` module creates is a specific instance of a general problem:

*   In the course of performing its duties, a routine is going to need to create a number of objects on behalf of the caller.

*   But the class that the routine would instantiate by default does not cover all possible cases.

*   So instead of hard-coding that default class and making customization impossible, the routine wants to let the caller specify which classes it will instantiate.

First, we’ll look at the Pythonic approach to this problem. Then we’ll start placing a series of restrictions on our Python code to more closely model legacy object oriented languages, until the Abstract Factory pattern emerges as the best solution within those limitations.

## The Pythonic approach: callable factories[¶](https://python-patterns.guide/gang-of-four/abstract-factory/#the-pythonic-approach-callable-factories "Link to this heading")

In Python, a “callable” — any object `f` that executes code when invoked using the syntax `f(a, b, c)` — is a first-class object. To be “first class” means that a callable can be passed as a parameter, returned as a return value, and can even be stored in a data structure like a list or dictionary.

First-class callables offer a powerful mechanism for implementing object “factories”, a fancy term for “routines that build and return new objects.”

A beginning Python programmer might expect that each time they need to supply a factory, they will be responsible for writing a function:

import json
from decimal import Decimal

def build_decimal(string):
    return Decimal(string)

print(json.loads(text, parse_float=build_decimal))

{'total': Decimal('9.61'), 'items': ['Americano', 'Omelet']}

This simple factory ran successfully! The number returned is a decimal instead of a float.

(Note my choice of a verb `build_decimal()` as the name of this function, instead of a noun like `decimal_factory()` — I find a function name easier to read when it tells me what the function _does_ instead of telling me what _kind_ of function it is.)

While the above function will certainly work, there is an elision we can perform thanks to the fact that Python types are themselves callables. Because `Decimal` is a callable taking a string argument and returning a decimal object instance, we can dispense with our own factory and pass the `Decimal` type directly to the JSON loader! Unless we need to edit the string first, like by removing a leading currency symbol, `Decimal` can completely replace our little factory:

print(json.loads(text, parse_float=Decimal))

{'total': Decimal('9.61'), 'items': ['Americano', 'Omelet']}

There is one implementation detail that deserves mention. If you study the `json` module you will discover that `load()` is simply a wrapper around the `JSONDecoder` class. How does the decoder instance itself support an alternative factory? Its initialization method stores the `parse_float` argument as an instance attribute, defaulting to Python’s built-in `float` type if no override was specified:

self.parse_float = parse_float or float

It can then invoke it later as `self.parse_float(…)`.

If you are interested in variations on this pattern — where a class uses its instance attributes to remember how it’s supposed to create a specific kind of object — then try reading about the [Factory Method](https://python-patterns.guide/gang-of-four/factory-method/) which explores several variations on this maneuver.

But to arrive at the Abstract Factory pattern, we need to head in a different direction. Here we’ll pursue what happens to an object factory itself — whether `Decimal()` or our hand-written `build_decimal()` — if we begin restricting the set of Python features we let ourselves use.

## Restriction: outlaw passing callables[¶](https://python-patterns.guide/gang-of-four/abstract-factory/#restriction-outlaw-passing-callables "Link to this heading")

What if Python didn’t let you pass callables as parameters?

That restriction would remove an entire dimension from Python’s flexibility. Instead of supporting both “nouns” and “verbs” as arguments — both class instances and callable functions — some legacy languages only support passing class instances. Under that restriction, every simple factory would need to pivot from a function to a method:

# In Python: a factory function.

def build_decimal(string):
    return Decimal(string.lstrip('$'))

# In some legacy languages: the code must
# move inside a class method instead.

class DecimalFactory(object):
    @staticmethod
    def build(string):
        return Decimal(string.lstrip('$'))

In traditional Object Oriented programming, the word “factory” is the name of this kind of class — a class that offers a method that builds an object. In naming the equivalent Python function `build_decimal()`, therefore, I’m not only indulging in my own preference for giving functions verb-names rather than noun-names, but being as precise as possible in naming: the “factory” is not the callable, but the class that holds it.

Instead of continuing our earlier example of JSON parsing, let’s switch to a simpler task that can fit in a couple of lines of code: parsing a comma-separated list of numbers. Here’s how the parser would invoke the builder method on our factory class.

class Loader(object):
    @staticmethod
    def load(string, factory):
        string = string.rstrip(',')  # allow trailing comma
        return [factory.build(item) for item in string.split(',')]

result = Loader.load('464.80, 993.68', DecimalFactory)
print(result)

[Decimal('464.80'), Decimal('993.68')]

Note that, thanks to the fact that Python classes offer static and class methods that can be invoked without an instance, we have not yet been reduced to needing to instantiate the factory class — we are simply passing the Python class in as a first-class object.

## Restriction: outlaw passing classes[¶](https://python-patterns.guide/gang-of-four/abstract-factory/#restriction-outlaw-passing-classes "Link to this heading")

Next, let’s also pretend that a Python class cannot be passed as a value, but that only object instances can be assigned to names and passed as parameters.

This restriction is going to prevent us from passing the `DecimalFactory` class as an argument to the `load()` method. Instead, we’re going to have to uselessly instantiate `DecimalFactory` and pass the resulting object:

f = DecimalFactory()

result = Loader.load('464.80, 993.68', f)
print(result)

[Decimal('464.80'), Decimal('993.68')]

Note the difference between this pattern and the [Factory Method](https://python-patterns.guide/gang-of-four/factory-method/). Here, we are neither asked nor required to subclass `Loader` itself in order to customize the objects it creates. Instead, object creation is entirely parametrized by the separate factory object we choose to pass in.

Note also the clear warning sign in the factory’s own code that `build()` should, in Python, not really be the method of an object. Scroll back up and read the method’s code. Where does it accept as an argument, or use in its result, the object `self` on which it is being invoked? It makes no use of it at all! The method never mentions `self` in its code. As Jack Diederich propounded in his famous talk [Stop Writing Classes](https://www.youtube.com/watch?v=o9pEzgHorH0), a method that never uses `self` should not actually be a method in Python. But such are the depths to which we’ve been driven by these artificial restrictions.

## Generalizing: the complete Abstract Factory[¶](https://python-patterns.guide/gang-of-four/abstract-factory/#generalizing-the-complete-abstract-factory "Link to this heading")

Two final moves will illustrate the full design pattern.

First, let’s expand our factory to create every kind of object that the loader needs to create — in this case, not just the numbers that are being parsed, but even the container that will hold them. Now that we have switched to instantiating the factory, we can write these as plain methods instead of static methods:

class Factory(object):
    def build_sequence(self):
        return []

    def build_number(self, string):
        return Decimal(string)

And here is an updated loader that uses this factory:

class Loader(object):
    @staticmethod
    def load(string, factory):
        sequence = factory.build_sequence()
        for substring in string.split(','):
            item = factory.build_number(substring)
            sequence.append(item)
        return sequence

f = Factory()
result = Loader.load('1.23, 4.56', f)
print(result)

[Decimal('1.23'), Decimal('4.56')]

Every choice it needs to make about object instantiation is deferred to the factory instead of taking place in the parser itself.

Second, consider the behavior of languages that force you to declare ahead of time the type of each method parameter. You would overly restrict your future choices if your code insisted that the `factory` parameter could only ever be an instance of this particular class `Factory` because then you could never pass in anything that didn’t inherit from it.

Instead, to more happily separate specification from implementation, you would create an abstract class. It’s this final step that merits the word “abstract” in the pattern’s name “Abstract Factory”. Your abstract class would merely promise that the `factory` argument to `load()` would be a class adhering to the required interface:

from abc import ABCMeta, abstractmethod

class AbstractFactory(metaclass=ABCMeta):

    @abstractmethod
    def build_sequence(self):
        pass

    @abstractmethod
    def build_number(self, string):
        pass

Once the abstract class is in place and `Factory` inherits from it, though, the operations that take place at runtime are exactly the same as they were before. The factory’s methods are called with various arguments, which direct them to create various kinds of object, which they construct and return without the caller needing to know the details.

It’s like something you might do in Python, but made overly complicated. So avoid the Abstract Factory and use callables as factories instead.

---

<!-- source: https://python-patterns.guide/gang-of-four/builder/ -->

_A “Creational Pattern” from the_[Gang of Four book](https://python-patterns.guide/gang-of-four/)

Verdict

The full-fledged Builder Pattern as imagined by the Gang of Four arranged for a single series of method calls to power the creation of several different object hierarchies — but that use of the pattern has turned out to be vanishingly rare in Python. Instead, the Builder is wildly popular simply for its convenience.

You might also have seen a more recent pattern calling itself the “Builder” which pairs each immutable class in a program with a more convenient builder class. That pattern, happily, is never necessary in Python since the language itself provides built-in syntactic support for optional constructor arguments.

Contents:

*   [The Builder Pattern](https://python-patterns.guide/gang-of-four/builder/#the-builder-pattern)

    *   [The Builder as convenience](https://python-patterns.guide/gang-of-four/builder/#the-builder-as-convenience)

    *   [Nuance](https://python-patterns.guide/gang-of-four/builder/#nuance)

    *   [Dueling builders](https://python-patterns.guide/gang-of-four/builder/#dueling-builders)

    *   [A degenerate case: simulating optional arguments](https://python-patterns.guide/gang-of-four/builder/#a-degenerate-case-simulating-optional-arguments)

The Builder pattern has a most interesting history. Its primary intent, as described by the Gang of Four in the very first sentence of their chapter on the pattern, has wound being the rarest purpose for which the pattern is used. Instead, the Builder is used almost everywhere for what the Gang of Four considered a secondary benefit: its convenience.

More recently, an even simpler pattern has adopted the name “Builder” that appears in certain less expressive programming languages to make up for their lack of optional parameters in a call to a constructor.

This article will start by describing the Builder pattern’s most popular use in Python programs. Next we will glance at what the Gang of Four thought the pattern’s primary purpose was going to be, and explore why it is rarely used that way in Python. Finally, for completeness, we will look at the more recent use of the pattern to help languages whose syntax is less flexible than Python’s.

## The Builder as convenience[¶](https://python-patterns.guide/gang-of-four/builder/#the-builder-as-convenience "Link to this heading")

The Builder pattern is wildly popular in Python because it lets client code stay simple and sleek even while directing the creation of an elaborate hierarchy of objects.

The formal definition is that the Builder pattern is present whenever a library lets you make a simple series of function and method calls that, behind the scenes, the library reacts to by building a whole hierarchy of objects. Thanks to the Builder pattern, the caller is exempted from needing to manually instantiate each object or understand how the objects fit together once constructed.

A classic example in Python is the [matplotlib](https://matplotlib.org/) library’s `pyplot` interface. It lets the caller build a simple plot with just a single line of code, and save the diagram to disk with just one line more:

import numpy as np
x = np.arange(-6.2, 6.2, 0.1)

import matplotlib.pyplot as plt
plt.plot(x, np.sin(x))
plt.savefig('sine.png')

What the pyplot interface has hidden from the caller is that more than a dozen objects had to be created for matplotlib to represent even this simple plot. Here, for example, are eight of the objects that were generated behind the scenes by the `plot()` call above:

>>> plt.gcf()
<Figure size 640x480 with 1 Axes>

>>> plt.gcf().subplots()
<matplotlib.axes._subplots.AxesSubplot object at 0x7ff910917a20>

>>> plt.gcf().subplots().bbox
TransformedBbox(
 Bbox(x0=0.125, y0=0.10999999999999999, x1=0.9, y1=0.88),
 BboxTransformTo(
 TransformedBbox(
 Bbox(x0=0.0, y0=0.0, x1=6.4, y1=4.8),
 Affine2D(
 [[100. 0. 0.]
 [ 0. 100. 0.]
 [ 0. 0. 1.]]))))

While matplotlib will let us provide more keyword arguments or make additional calls to customize the plot, `pyplot` is happy to insulate us from all of the details of how plots are represented as objects.

The Builder pattern is now deeply ingrained in Python culture thanks in part to the pressure that library authors feel to make the sample code on their front page as impressively brief as possible. But even in the face of this pressure, there still exist libraries that expect you — their caller — to build an entire object hierarchy yourself in the course of using the library.

The fact that some libraries rely on their callers to tediously instantiate objects is even used as advertisement by their competitors. For example, the [Requests library](http://docs.python-requests.org/en/master/) famously introduces itself to users by comparing its one-liner for an HTTP request with authentication to the same maneuver performed with the old [urllib2](https://docs.python.org/2/library/urllib2.html) Standard Library module — which, in fairness, does require the caller to build a small pile of objects any time they want to do anything interesting. The “Examples” section of the `urllib2` documentation provides an illustration:

import urllib2

# Create an OpenerDirector with support for Basic HTTP Authentication...

auth_handler = urllib2.HTTPBasicAuthHandler()
auth_handler.add_password(realm='PDQ Application',
                          uri='https://mahler:8092/site-updates.py',
                          user='klem',
                          passwd='kadidd!ehopper')
opener = urllib2.build_opener(auth_handler)

# ...and install it globally so it can be used with urlopen.

urllib2.install_opener(opener)
urllib2.urlopen('http://www.example.com/login.html')

Had the Builder pattern been used here, the library would instead have offered functions or methods that concealed from client code the structure and classes in the opener - builder - authentication handler hierarchy.

## Nuance[¶](https://python-patterns.guide/gang-of-four/builder/#nuance "Link to this heading")

My claim that the matplotlib `pyplot` interface is a Builder is complicated by the second-to-last paragraph in the Gang of Four’s chapter on the Builder:

> “Builder **returns the product as a final step**, but as far as the Abstract Factory pattern is concerned, the product gets returned immediately.”

While this stipulation focuses on the difference between the Builder and the [Abstract Factory](https://python-patterns.guide/gang-of-four/abstract-factory/), it makes clear that — for the Gang of Four — both patterns are supposed to conclude with the return of the constructed object to the caller. Absent the crucial final step of returning the object that has been built, the Builder arguably devolves into the Facade pattern instead.

So by the strict definition, `pyplot` might not qualify as a Builder in my example code above because I never ask for an actual reference to the object that my `plot()` call constructed. To rescue my example in case anyone decides to press the point, I can ask for a reference to the plot and ask the plot itself to save a rendered image to a file.

plt.plot(x, np.sin(x))
sine_figure = plt.gcf()  # “gcf” = “get current figure”
sine_figure.savefig('sine.png')

Such are the demands of pedantry: an extra line of code.

## Dueling builders[¶](https://python-patterns.guide/gang-of-four/builder/#dueling-builders "Link to this heading")

When the Gang of Four introduced the Builder, they had greater ambitions for the pattern than mere convenience and encapsulation. The opening sentence of their chapter on the Builder declared the following “Intent”:

> “Separate the construction of a complex object from its representation so that the same construction process can create different representations.”

For the Gang of Four, then, the Builder pattern is only operating at full tilt when a library offers several implementations of the same Builder, each of which returns a different hierarchy of objects in response to the same series of client calls.

I cannot find evidence that the full-tilt Builder pattern is in frequent use across today’s most popular python libraries.

Why has the pattern not come into widespread use?

I think the answer is the supremacy of data, and of data structures, as the common currency that is usually passed between one phase of a Python program’s execution and the next. To understand why, let’s turn to the Gang of Four’s own sample code. Here, for example, is one situation in which their Builder is placed as it responds to calls describing the creation of a maze (the example has been lightly edited to translate it into Python):

class StandardMazeBuilder(object):
    # ...
    def build_door(n1, n2):
        room1 = self._current_maze.get_room(n1)
        room2 = self._current_maze.get_room(n2)
        door = Door(r1, r2)

        room1.set_side(common_wall(r1, r2), d)
        room2.set_side(common_wall(r2, r1), d);

Notice the awkward responsive pattern into which the code is forced. It knows that a maze is under construction, but has to recover a reference to the maze by asking `self` for its `current_maze` attribute. It then has to make several adjustments to update the room objects with the new information so that subsequent interactions will start from a new state. This looks suspiciously like I/O code that has been contorted into a series of callbacks, each needing to re-fetch and re-assemble the current state of the world in order to ratchet its state machine forward one further click.

If a modern Python Library does want to drive two very different kinds of activity from the same series of client constructor calls, it would be very unusual for that library to offer two completely separate implementations of the same Builder interface — two builders that both have to be capable of being prodded through the same series of incremental client-driven updates to produce a coherent result.

Instead, modern python libraries are overwhelmingly likely to have a single implementation of a given Builder, one that produces a single well-defined intermediate representation from the caller’s function and method invocations. That representation, whether publicly documented or private and internal to the library, can then be provided as the input to any number of downstream transformation or output routines — whose processing will now be simpler because they are free to roam across the intermediate data structure at their own pace and in whatever order they want.

To compare the popularity of callback programming with the popularity of foregrounding an intermediate representation, compare the paltry number of Python libraries that use the [Standard Library `lmx.sax` package](https://docs.python.org/3/library/xml.sax.html) — which learns about a document by responding to a long series of `startElement()` and `endElement()` calls — with the wide popularity of the [ElementTree](https://docs.python.org/3/library/xml.etree.elementtree.html) API that presumes the XML is already completely parsed and offers the caller a Document Object Module to traverse in whatever order it wants.

It is, therefore, probably Python’s very rich collection of data types for representing deep compound information — tuples, lists, dictionaries, classes — and the convenience of writing code to traverse them that has produced almost an entire absence of the full-tilt Builder pattern from today’s popular Python libraries.

## A degenerate case: simulating optional arguments[¶](https://python-patterns.guide/gang-of-four/builder/#a-degenerate-case-simulating-optional-arguments "Link to this heading")

For the sake of completeness, I should describe an alternative Builder pattern that differs from the pattern described by the Gang of Four, in case you have seen it in blog posts or books and have been confused by the difference. It has arisen recently in some of the less convenient programming languages than Python, and substitutes for those languages’ lack of optional parameters.

The degenerate Builder addresses this problem:

*   A programmer designs a class with immutable attributes. Once a class instance is created, its attributes will be impossible to modify.

*   The class has not just one or two, but many attributes — imagine that it has a dozen.

*   The programmer is trapped in a programming language that lacks Python’s support for optional arguments. A call to the class constructor will need to supply a value for every single attribute each time the class is instantiated.

You can imagine the verbose and unhappy consequences. Not only will every single object instantiation have to specify every one of the dozen attributes, but if the language does not support keyword arguments then each value in the long list of attributes will also be unlabeled. Imagine reading a long list of values like `None``None``0``''``None` and trying to visually pair each value with the corresponding name in the attribute list. A comment next to each value can improve readability, but the language will not provide any guard rail if a later edit accidentally moves the comments out of sync with the actual attributes.

To escape their dilemma and achieve some approximation of the happy brevity that Python programmers take for granted, programmers facing this situation can supplement each class they write with a second class that serves as a builder for the first. The differences between the builder and the class it constructs are that:

*   The Builder class carries all the same attributes as the target class.

*   The Builder class is _not_ immutable.

*   The Builder class requires very few arguments to instantiate. Most or all of its attributes start off with default values.

*   The Builder offers a mechanism for each attribute that starts with a default value to be rewritten with a different value.

*   Finally, the Builder offers a method that creates an instance of the original immutable class whose attributes are copied from the corresponding attributes of the Builder instance.

Here is a tiny example in Python — non-tiny examples are, alas, painful to read because of their rampant repetition:

# Slightly less convenient in Python < 3.6:

from typing import NamedTuple

class Port(NamedTuple):
    number: int
    name: str = ''
    protocol: str = ''

# Real Python code takes advantage of optional arguments
# to specify whatever combination of attributes it wants:

Port(2)
Port(7, 'echo')
Port(69, 'tftp', 'UDP')

# Keyword arguments even let you skip earlier arguments:

Port(517, protocol='UDP')

# But what if Python lacked optional arguments?
# Then we might engage in contortions like:

class PortBuilder(object):
    def  __init__ (self, port):
        self.port = port
        self.name = None
        self.protocol = None

    def build(self):
        return Port(self.port, self.name, self.protocol)

# The Builder lets the caller create a Port without
# needing to specify a value for every attribute.
# Here we skip providing a “name”:

b = PortBuilder(517)
b.protocol = 'UDP'
b.build()

At the expense of a good deal of boilerplate — which becomes even worse if the author insists on writing a setter for each of the Builder’s attributes — this pattern allows programmers in deeply compromised programming languages to enjoy some of the same conveniences that are built into the design of the Python “call” operator.

This is clearly not the Builder pattern from the Gang of Four. It fails to achieve every one of the “Consequences” their chapter lists for the Builder pattern: its `build()` method always returns the same class, instead of exercising the freedom to return any of several subclasses of the target class; it does not isolate the caller from how the target class represents its data since the builder and target attributes correspond one-to-one; and no fine control over the build process is achieved since the effect is the same — though less verbose — as if the caller had simply instantiated the target class directly.

Hopefully you will never see a Builder like this in Python, even to correct the awkward fact that named tuples provide no obvious way to set a default value for each field — the [excellent answers to this Stack Overflow question](https://stackoverflow.com/questions/11351032/namedtuple-and-default-values-for-optional-keyword-arguments) provide several more Pythonic alternatives. But you might see it in other languages when reading or even porting their code, in which case you will want to recognize the pattern so that you can replace it with something simpler if the code is re-implemented in Python.

---

<!-- source: https://python-patterns.guide/gang-of-four/factory-method/ -->

_A “Creational Pattern” from the_[Gang of Four book](https://python-patterns.guide/gang-of-four/)

Verdict

The “Factory Method” pattern is a poor fit for Python. It was designed for underpowered programming languages where classes and functions can’t be passed as parameters or stored as attributes. In those languages, the Factory Method serves as an awkward but necessary escape route. But it’s not a good design for Python applications.

You will often create objects in Python that themselves need to turn around and create more objects. Imagine an HTTP connection pool, for example, that sometimes needs to create new connections to replace old connections as they time out and close.

Now comes the challenge. What if your program will run behind a special corporate proxy, and the HTTP connection pool will only be able to communicate if it creates and uses specially configured network connections instead of the generic sockets that it usually creates?

The Factory Method is one pattern by which the HTTP connection pool class could offer you a way to choose what kind of connection it creates. Before learning how this awkward pattern works, let’s review the Pythonic design patterns that solve the same problem.

## Dodge: use Dependency Injection[¶](https://python-patterns.guide/gang-of-four/factory-method/#dodge-use-dependency-injection "Link to this heading")

First, we should stop for a moment and double-check something. Does the class you’re designing _really_ need to go around creating other classes?

If you know up front all the objects that the class will need, you should consider providing them to the class yourself through Dependency Injection.

You will see excellent examples of this simpler pattern everywhere that Python libraries let you pass an already-open file object instead of making you supply a path and insisting on opening the file themselves. Take the Standard Library’s JSON parser as an example. Instead of asking for a path, its `load()` method lets you open the file:

import json
with open('input_data.json') as f:
    data = json.load(f)

By leaving you in charge of instantiating the file object, this maneuver accomplishes many goals at once.

*   **Decoupling:** the library doesn’t need to know all the parameters accepted by the open() method, and doesn’t need to accept every one of them as a parameter itself. If the file object were to grow more creation parameters in the future, `json.load()` won’t need to change.

*   **Efficiency:** If you already have the file open for other reasons, you can go ahead and provide the open file object. The library won’t insist on re-opening the file. This is crucial if the file is a read-once source of data like an anonymous pipe.

*   **Flexibility:** You can pass any file-like object you want. It can be a subclass of the standard file object, or be completely independent. You could pass a `StringIO` that operates directly on data in RAM instead of needing the JSON written to disk first. Or you could offer a wrapper around a socket that lets you parse JSON data as it arrives off the network without needing to be stored locally first.

In a simple case like this, the Dependency Injection pattern completely eliminates the need for an object like a JSON parser to have its design made more complicated by the details of how other objects get created.

So (a)if your class always needs a particular object built, and (b)if users will normally want to at least customize the parameters with which it is instantiated, you should strongly consider Dependency Injection. In that case, you might want to read Miško Hevery’s [2008 post about dependency injection](https://web.archive.org/web/20230321074829/http://misko.hevery.com/2008/10/21/dependency-injection-myth-reference-passing/) for an important note about the dangers of applying Dependency Injection halfway!

## Instead: use a Class Attribute Factory[¶](https://python-patterns.guide/gang-of-four/factory-method/#instead-use-a-class-attribute-factory "Link to this heading")

The next alternative comes to us from the 1990s. The class that needs to be created can be attached as an attribute on the class that will be doing the creating.

You can see this pattern in some of the older modules in the Python Standard Library. For example, when an `HTTPConnection` is done sending a request, it expects to receive and parse a response. But what class should it use to parse and represent the response? What if you happen to be talking to a server that sends non-standard information in its response for which you require special handling?

What I will here call the Class Attribute Factory pattern takes advantage of the fact that classes are first-class objects in Python. It simply attaches the class as an attribute of the class that will be doing the creating. You’ll find the following code in the Standard Library:

class HTTPConnection:
    ...
    response_class = HTTPResponse
    ...
    def getresponse(self):
        ...
        response = self.response_class(self.sock, method=self._method)
        ...

This gives the code using the `HTTPConnection` complete control over what happens when it is time to build a response. All it has to do is create a subclass and use the subclass instead:

class SpecialHTTPConnection(HTTPConnection):
    response_class = SpecialHTTPResponse

That’s all there is to it! While subclassing generally means that a software design is running at least somewhat against the grain of the Python language, the approach will still work well. The subclass will behave exactly like a normal Standard Library HTTP connection except when the moment comes to instantiate a response. At that point the connection will access its `response_class` attribute, receive the alternative class you provided instead of the normal one, and the alternative response class will then be in control.

There is more flexibility here we should explore, but first let’s look at the more modern alternative to the Class Attribute Factory.

## Instead: use an Instance Attribute Factory[¶](https://python-patterns.guide/gang-of-four/factory-method/#instead-use-an-instance-attribute-factory "Link to this heading")

Why should you have to subclass an object merely to customize its behavior?

It’s a serious question — very serious, for at one point in the history of programming some adherents of a doctrine called “object orientation” were suggesting that if you wanted a button that said “Submit” that you shouldn’t be able to simply instantiate a button with a parameter like `label="Submit"` but that you should instead have to subclass the button and override its default `label()` method to return something new.

Happily, an alternative to subclass-powered customization has swept the Python community: what I’ll call the Instance Attribute Factory. Among the many good examples of its practice is the `json` module in the Standard Library, which was added around 2008.

Here’s one example from the `json` module. Every time the JSON module encounters a number in its input, it has to instantiate some kind of Python object capable of representing the number. But which number class should it instantiate? An integer, if the fractional part of the number is zero? A float, the only numeric type in JavaScript? Or a `Decimal` that’s guaranteed to not lose any precision?

Watch how elegantly the `json` module handles the question:

class JSONDecoder(object):
    ...
    def  __init__ (self, ... parse_float=None, ...):
        ...
        self.parse_float = parse_float or float
        ...

Whenever it encounters a number in its input, it simply calls `self.parse_float()` with the string as input.

This is Python code that’s running on all pistons. If the developer does not intervene, each number is interpreted using a lighting-fast call to the `float` type itself. If instead the developer has provided their own callable for parsing numbers, then that callable is transparently used instead.

The beauty is that it all happens without a single additional class! Instead of forcing the programmer to create a new class each time they want to customize behavior, individual `JSONDecoder` instances can each be configured directly. You can create a custom decoder with a single line of code:

from decimal import Decimal
from json import JSONDecoder

my_decoder = JSONDecoder(parse_float=Decimal)

Besides the benefits of clarity and brevity, an advantage of customizing an object through its parameters is that parameters compose so beautifully in Python. If several pieces of code have parameters for the decoder that they need to combine, the task is no more difficult than building an empty `dict` and then using `update()` to fill it with each set of parameters, setting the parameters last that should be allowed to override the earlier ones.

## Instance attributes override class attributes[¶](https://python-patterns.guide/gang-of-four/factory-method/#instance-attributes-override-class-attributes "Link to this heading")

I should admit that the previous two design patterns are not as completely different as I have tried to make it sound. At bottom, both classes — the `HTTPConnection` and the `JSONDecoder` — make the exact same move when they are ready to create a new object: they start with `self` and use `.` to access some specific attribute on it. The only difference in the two design patterns above is in how they choose to supply the attribute. The first pattern happens to use a class attribute, while the second uses an instance attribute.

But the two are not mutually exclusive. There is no rule that if you have a class attribute named `.response_class` that you can’t also have an instance attribute named `.response_class` — and the rule in the case where you have both is simple: the instance attribute wins.

Which means I should admit that, really, even though I made a big deal about claiming that the `HTTPConnection` forces you to subclass it, it’s not true. You can override the default but just setting an instance attribute instead, just like the `JSONDecoder` does! The only difference is that the `HTTPConnection` won’t give you any help — you’ll have to reach in and set the instance attribute yourself:

conn = HTTPConnection()
conn.response_class = SpecialHTTPResponse

So even when an old-fashioned class looks like it wants you to create a subclass that specifies a new value for one of its class attributes, you can often use the more modern Instance Attribute Factory instead!

There are tiny differences in semantics and performance between class attributes and instance attributes, but I’ll refer you to the Python documentation and to Stack Overflow if you think your code is wandering towards an edge case where you care about the difference.

In general you should choose between the above patterns based on readability. If you can imagine developers ever wanting to customize object creation, then go ahead and try making the object creation routine (the “factory”) a parameter in your `__init__()` method and store it as an instance attribute. If instead you think that customization will be extremely rare, then make it a class attribute, remembering that the developer can always reach in and override it in those rare cases where they need to.

## Any callables accepted[¶](https://python-patterns.guide/gang-of-four/factory-method/#any-callables-accepted "Link to this heading")

In the examples above, we used actual classes like `Decimal` and the fictional `SpecialHTTPResponse` when setting an attribute like `response_class` or `parse_float`. But you’ll note that the only thing the callers cared about was that these classes were callables. There’s happily no `new` keyword in Python, so object instantiation looks exactly like a normal function or method call.

This means that you can substitute a function for any of these callbacks, and it will work just as well! For example, you could provide the JSON decoder with a function like this as its `parse_float` parameter:

def parse_number(string):
    if '.' in string:
        return Decimal(string)
    return int(string)

You can provide not only a function, but any other kind of callable as well — maybe a bound method, or a class method like an alternative constructor. You could even provide a callable that you’ve spun up dynamically using functional programming techniques like partial application:

from decimal import Context, ROUND_DOWN
from functools import partial

parse_number = partial(Decimal, context=Context(2, ROUND_DOWN))

Feel free to enjoy this Pythonic freedom of providing any kind of callable, and not limiting yourself to just providing classes, whether you are using the Class Attribute Factory or an Instance Attribute Factory.

## Implementing[¶](https://python-patterns.guide/gang-of-four/factory-method/#implementing "Link to this heading")

Having described the happy alternatives, I should finish by showing you the Factory Method itself. Imagine that you were using a language where:

*   Classes are not first-class objects. You are not allowed to leave a class sitting around as an attribute of either a class instance or of another class itself.

*   Functions are not first-class objects. You’re not allowed to save a function as an instance of a class or class instance.

*   No other kind of callable exists that can be dynamically specified and attached to an object at runtime.

Under such dire constraints, you would turn to subclassing as a natural way to attach verbs — new actions — to existing classes, and you might use method overriding as a basic means of customizing behavior. And if on one of your classes you designed a special method whose only purpose was to isolate the act of creating new objects, then you’d be using the Factory Method pattern.

The Factory Method pattern can often be observed anywhere that code from an underpowered but object-oriented language has been translated straight into Python. The `logging` module from the Standard Library comes immediately to mind. Here’s an excerpt:

class Handler(Filterer):
    ...
    def  __init__ (self, level=NOTSET):
        ...
        self.createLock()
    ...
    def createLock(self):
 """
 Acquire a thread lock for serializing access to the underlying I/O.
 """
        self.lock = threading.RLock()
    ...

What if you wanted to create a `Handler` that uses a special kind of lock? The intention here is that you subclass `Hander` and override `createLock()` to return your own favorite kind of lock instead. It’s a clunky approach, it takes several lines of code, and it won’t compose well if there are several ways you want to customize `Handler` objects in a variety of situations — you’ll wind up with classes all over the place.

But it will work.

It just won’t be very Pythonic.

---

<!-- source: https://python-patterns.guide/gang-of-four/prototype/ -->

_A “Creational Pattern” from the_[Gang of Four book](https://python-patterns.guide/gang-of-four/)

Verdict

The Prototype pattern isn’t necessary in a language powerful enough to support first-class functions and classes.

It is almost embarrassing how many good alternatives Python offers to the Prototype pattern.

As the problem and its solutions are simple, this article will be brief. We will define the problem, list several Pythonic solutions, and finish by studying how the Gang of Four solved the same problem under more onerous constraints.

## The problem[¶](https://python-patterns.guide/gang-of-four/prototype/#the-problem "Link to this heading")

The Prototype Pattern suggests a mechanism by which a caller can provide a framework with a menu of classes to instantiate when the user — or some other runtime source of dynamic requests — selects the classes from a menu of choices.

The problem would be a much simpler one if none of the classes in the menu needed `__init__()` arguments:

class Sharp(object):
    "The symbol ♯."

class Flat(object):
    "The symbol ♭."

Instead, the Prototype pattern is called into play when classes will need to be instantiated that require arguments:

class Note(object):
    "Musical note 1 ÷ `fraction` measures long."
    def  __init__ (self, fraction):
        self.fraction = fraction

It is this situation — supplying a framework with a menu of classes that will need to be instantiated with pre-specified argument lists — that the Prototype pattern is designed to address.

## Pythonic solutions[¶](https://python-patterns.guide/gang-of-four/prototype/#pythonic-solutions "Link to this heading")

Python offers several possible mechanisms for supplying a framework with the classes we want to instantiate and the arguments we want them instantiated with.

In the examples below, we will provide the menu of classes in a simple data structure — a Python dictionary — but the same principles apply even if the framework wants the menu items supplied in some other data structure, or supplied separately in a series of `register()` calls.

One approach is to design the classes so that they only need positional arguments, not keyword arguments. The framework will then be able to store the arguments as a simple tuple, which can be supplied separately from the class itself — the familiar approach of the Standard Library [Thread](https://docs.python.org/3/library/threading.html#thread-objects) class which asks for a callable `target=` separately from the `args=(...)` it will be passed. Our menu items might look like:

menu = {
    'whole note': (Note, (1,)),
    'half note': (Note, (2,)),
    'quarter note': (Note, (4,)),
    'sharp': (Sharp, ()),
    'flat': (Flat, ()),
}

Alternatively, each class and arguments could live in the same tuple:

menu = {
    'whole note': (Note, 1),
    'half note': (Note, 2),
    'quarter note': (Note, 4),
    'sharp': (Sharp,),
    'flat': (Flat,),
}

The framework would then invoke each callable using some variation of `tup[0](*tup[1:])`.

In the more general case, though, a class might require not just positional arguments but also keyword arguments. In response, we could pivot to providing simple callables to the framework, using lambda expressions for the classes that require arguments:

menu = {
    'whole note': lambda: Note(fraction=1),
    'half note': lambda: Note(fraction=2),
    'quarter note': lambda: Note(fraction=4),
    'sharp': Sharp,
    'flat': Flat,
}

While lambdas don’t support quick introspection — it isn’t easy for a framework or debugger to inspect them to learn what callable they will invoke or what arguments they will supply — they work fine if all the framework needs to do is invoke them.

Another approach is to use a [partial](https://docs.python.org/3/library/functools.html#functools.partial) for each item, which packages together a callable with both positional and keywords arguments that will be supplied when the partial itself is later called:

from functools import partial

# Keyword arguments for illustration only;
# in this case could instead write ‘partial(Note, 1)’

menu = {
    'whole note': partial(Note, fraction=1),
    'half note': partial(Note, fraction=2),
    'quarter note': partial(Note, fraction=4),
    'sharp': Sharp,
    'flat': Flat,
}

I will stop there, though you are free to keep imagining more alternatives — for example, you could supply a class, a tuple, and a dictionary `(cls, args, kw)` for each menu item and the framework would call `cls(*args, **kw)` when each menu item is selected. The choices in Python for tackling this problem are numerous because classes and functions in Python are first-class and are therefore eligible to be passed as arguments and stored in data structures just like any other objects.

## Implementing[¶](https://python-patterns.guide/gang-of-four/prototype/#implementing "Link to this heading")

But the Gang of Four did not have the luxury of such easy circumstances as Python programmers enjoy. Armed with only polymorphism and the method call, they sallied forth to create a workable pattern.

You might at first imagine that, in the absence of tuples and the ability to apply them as argument lists, we are going to need factory classes which will each remember a particular list of arguments and then supply those arguments when they are asked for a new object:

# What the Prototype pattern avoids:
# needing one factory for every class.

class NoteFactory(object):
    def  __init__ (self, fraction):
        self.fraction = fraction

    def build(self):
        return Note(self.fraction)

class SharpFactory(object):
    def build(self):
        return Sharp()

class FlatFactory(object):
    def build(self):
        return Flat()

Fortunately, the situation is not so grim. If you re-read the factory classes above, you will notice that they each look similar — eerily similar — remarkably similar! — to the target classes we want to create. The `NoteFactory`, exactly like the `Note` itself, stores an attribute `fraction`. The stack of factories winds up looking, at least in their attribute lists, like the stack of classes we want to instantiate.

This symmetry suggest a way to solve our problem without having to mirror each class with a factory. What if we used the original objects themselves to store the arguments, and gave them the ability to provide new instances?

The result is the Prototype pattern! All of the factory classes disappear. Instead, each instance gains a `clone()` method to which it responds by building a new instance with exactly the same arguments it received:

# The Prototype pattern: teach each object
# instance how to build copies of itself.

class Note(object):
    "Musical note 1 ÷ `fraction` measures long."
    def  __init__ (self, fraction):
        self.fraction = fraction

    def clone(self):
        return Note(self.fraction)

class Sharp(object):
    "The symbol ♯."
    def clone(self):
        return Sharp()

class Flat(object):
    "The symbol ♭."
    def clone(self):
        return Flat()

While we could make this example more complicated — for example, each `clone()` method should probably call `type(self)` instead of hard-coding its class name, in case the method gets called on a subclass — this at least illustrates the pattern. The Prototype Pattern is not as convenient as the mechanisms available in the Python language, but this clever simplification made it much easier for the Gang of Four to accomplish parametrized object creation in some of the underpowered object oriented languages that were popular last century.

---

<!-- source: https://python-patterns.guide/gang-of-four/singleton/ -->

_A “Creational Pattern” from the_[Gang of Four book](https://python-patterns.guide/gang-of-four/)

Verdict

Python programmers almost never implement the Singleton Pattern as described in the [Gang of Four book](https://python-patterns.guide/gang-of-four/), whose Singleton class forbids normal instantiation and instead offers a class method that returns the singleton instance. Python is more elegant, and lets a class continue to support the normal syntax for instantiation while defining a custom `__new__()` method that returns the singleton instance. But an even more Pythonic approach, if your design forces you to offer global access to a singleton object, is to use [The Global Object Pattern](https://python-patterns.guide/python/module-globals/) instead.

## Disambiguation[¶](https://python-patterns.guide/gang-of-four/singleton/#disambiguation "Link to this heading")

Python was already using the term _singleton_ before the “Singleton Pattern” was defined by the object oriented design pattern community. So we should start by distinguishing the several meanings of “singleton” in Python.

1.   A tuple of length one is called a _singleton._ While this definition might surprise some programmers, it reflects the original definition of a singleton in mathematics: a set containing exactly one element. The Python Tutorial itself introduces newcomers to this definition when its chapter on [Data Structures](https://docs.python.org/3/tutorial/datastructures.html) calls a one-element tuple a “singleton” and the word continues to be used in that sense through the rest of Python’s documentation. When the [Extending and Embedding](https://docs.python.org/3/extending/extending.html#calling-python-functions-from-c) guide says, “To call the Python function … with one argument, pass a singleton tuple,” it means a tuple containing exactly one item.

2.   Modules are “singletons” in Python because `import` only creates a single copy of each module; subsequent imports of the same name keep returning the same module object. For example, when the [Module Objects](https://docs.python.org/3/c-api/module.html) chapter of the Python/C API Reference Manual asserts that “Single-phase initialization creates singleton modules,” it means by a “singleton module” a module for which only one object is ever created.

3.   A “singleton” is a class instance that has been assigned a global name through [The Global Object Pattern](https://python-patterns.guide/python/module-globals/). For example, the official Python Programming FAQ answers the question [“How do I share global variables across modules?”](https://docs.python.org/3/faq/programming.html#how-do-i-share-global-variables-across-modules) with the assertion that in Python “using a module is also the basis for implementing the Singleton design” — because not only can a module’s global namespace store constants (the FAQ’s example is `x = 0` shared between several modules), but mutable class instances as well.

4.   Individual flyweight objects that are examples of [The Flyweight Pattern](https://python-patterns.guide/gang-of-four/flyweight/) are often called “singleton” objects by Python programmers. For example, a comment inside the Standard Library’s `itertoolsmodule.c` asserts that “CPython’s empty tuple is a singleton” — meaning that the Python interpreter only ever creates a single empty tuple object, which `tuple()` returns over and over again every time it’s passed a zero-length sequence. A comment in `marshal.c` similarly refers to the “empty frozenset singleton.” But neither of these singleton objects is an example of the Gang of Four’s Singleton Pattern, because neither object is the sole instance of its class: `tuple` lets you build other tuples besides the empty tuple, and `frozenset` lets you build other frozen sets. Similarly, the `True` and `False` objects are a pair of flyweights, not examples of the Singleton Pattern, because neither is the sole instance of `bool`.

5.   Finally, Python programmers on a few rare occasions do actually mean “The Singleton Pattern” when they call an object a “singleton”: the lone object returned by its class every time the class is called.

The Python 2 Standard Library included no examples of the Singleton Pattern. While it did feature singleton objects like `None` and `Ellipsis`, the language provided access to them through the more Pythonic [Global Object Pattern](https://python-patterns.guide/python/module-globals/) by giving them names in the `__builtin__` module. But their classes were not callable:

>>> type(None)
<type 'NoneType'>
>>> NoneType = type(None)
>>> NoneType()
TypeError: cannot create 'NoneType' instances
>>> type(Ellipsis)()
TypeError: cannot create 'ellipsis' instances

In Python 3, however, the classes were upgraded to use the Singleton Pattern:

>>> NoneType = type(None)
>>> print(NoneType())
None
>>> type(Ellipsis)()
Ellipsis

This makes life easier for programmers who need a quick callable that always returns `None`, though such occasions are rare. In most Python projects these classes are never called and the benefit remains purely theoretical. When Python programmers need the `None` object they use [The Global Object Pattern](https://python-patterns.guide/python/module-globals/) and simply type its name.

## The Gang of Four’s implementation[¶](https://python-patterns.guide/gang-of-four/singleton/#the-gang-of-fours-implementation "Link to this heading")

The C++ language that the Gang of Four were targeting imposed a distinct syntax on object creation, that looked something like:

# Object creation in a language
# that has a “new” keyword.

log = new Logger()

A line of C++ that says `new` always creates a new class instance — it never returns a singleton. In the presence of this special syntax, what were their options for offering singleton objects?

1.   The Gang of Four did not take the easy way out and use [The Global Object Pattern](https://python-patterns.guide/python/module-globals/) because it did not work particularly well in early versions of the C++ language. There, global names all shared a single crowded global namespace, so elaborate naming conventions were necessary to prevent names from different libraries from colliding. The Gang judged that adding both a class and its singleton instance to the crowded global namespace would be excessive. And since C++ programmers couldn’t control the order in which global objects were initialized, no global object could depend on being able to call any other, so the responsibility of initializing globals often fell on client code.

2.   There was no way to override the meaning of `new` in C++, so an alternative syntax was necessary if all clients were to receive the same object. It was, though, at least possible to make it a compile-time error for client code to call `new` by marking the class constructor as either `protected` or `private`.

3.   So the Gang of Four pivoted to a class method that would return the class’s singleton object. Unlike a global function, a class method avoided adding yet another name to the global namespace, and unlike a static method, it could support subclasses that were singletons as well.

How could Python code illustrate their approach? Python lacks the complications of `new`, `protected`, and `private`. An alternative is to raise an exception in `__init__()` to make normal object instantiation impossible. The class method can then use a dunder method trick to create the object without triggering the exception:

# What the Gang of Four’s original Singleton Pattern
# might look like in Python.

class Logger(object):
    _instance = None

    def  __init__ (self):
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls):
        if cls._instance is None:
            print('Creating new instance')
            cls._instance = cls. __new__ (cls)
            # Put any initialization here.
        return cls._instance

This successfully prevents clients from creating new instances by calling the class:

log = Logger()

Traceback (most recent call last):
  ...
RuntimeError: Call instance() instead

Instead, callers are instructed to use the `instance()` class method, which creates and returns an object:

log1 = Logger.instance()
print(log1)

Creating new instance
<Logger object at 0x7f0ff5e7c080>

Subsequent calls to `instance()` return the singleton without repeating the initialization step (as we can see from the fact that “Creating new instance” isn’t printed again), exactly as the Gang of Four intended:

log2 = Logger.instance()
print(log2)
print('Are they the same object?', log1 is log2)

<Logger object at 0x7f0ff5e7c080>
Are they the same object? True

There are more complicated schemes that I can imagine for implementing the original Gang of Four class method in Python, but I think the above example does the best job of illustrating the original scheme with the least magic possible. Since the Gang of Four’s pattern is not a good fit for Python anyway, I’ll resist the temptation to iterate on it further, and instead move on to how the pattern is best supported in Python.

## A more Pythonic implementation[¶](https://python-patterns.guide/gang-of-four/singleton/#a-more-pythonic-implementation "Link to this heading")

In one sense, Python started out better prepared than C++ for the Singleton Pattern, because Python lacks a `new` keyword that forces a new object to be created. Instead, objects are created by invoking a callable, which imposes no syntactic limitation on what operation the callable really performs:

log = Logger()

To let authors take control of calls to a class, Python 2.4 added the `__new__()` dunder method to support alternative creational patterns like the Singleton Pattern and [The Flyweight Pattern](https://python-patterns.guide/gang-of-four/flyweight/).

The Web is replete with Singleton Pattern recipes featuring `__new__()` that each propose a more or less complicated mechanism for working around the method’s biggest quirk: the fact that `__init__()` always gets called on the return value, whether the object that’s being returned is new or not. To make my own example simple, I will simply not define an `__init__()` method and thus avoid having to work around it:

# Straightforward implementation of the Singleton Pattern

class Logger(object):
    _instance = None

    def  __new__ (cls):
        if cls._instance is None:
            print('Creating the object')
            cls._instance = super(Logger, cls). __new__ (cls)
            # Put any initialization here.
        return cls._instance

The object is created on the first call to the class:

log1 = Logger()
print(log1)

Creating the object
<Logger object at 0x7fa8e9cf7f60>

But the second call returns the same instance. The message “Creating the object” does not print, nor is a different object returned:

log2 = Logger()
print(log2)
print('Are they the same object?', log1 is log2)

<Logger object at 0x7fa8e9cf7f60>
Are they the same object? True

The example above opts for simplicity, at the expense of doing the `cls._instance` attribute lookup twice in the common case. For programmers who cringe at such waste, the result can of course be assigned a name and re-used in the return statement. And various other improvements can be imagined that would result in faster bytecode. But however elaborately tweaked, the above pattern is the basis of every Python class that hides a singleton object behind what reads like normal class instantiation.

## Verdict[¶](https://python-patterns.guide/gang-of-four/singleton/#verdict "Link to this heading")

While the Gang of Four’s original Singleton Pattern is a poor fit for a language like Python that lacks the concepts of `new`, `private`, and `protected`, it’s not as easy to dismiss the pattern when it’s built atop `__new__()` — after all, singletons were part of the reason the `__new__()` dunder method was introduced!

But the Singleton Pattern in Python does suffer from several drawbacks.

A first objection is that the Singleton Pattern’s implementation is difficult for many Python programmers to read. The alternative [Global Object Pattern](https://python-patterns.guide/python/module-globals/) is easy to read: it’s simply the familiar assignment statement, placed up at a module’s top level. But a Python programmer reading a `__new__()` method for the first time is probably going to have to stop and look for documentation to understand what’s going on.

A second objection is that the Singleton Pattern makes calls to the class, like `Logger()`, misleading for readers. Unless the designer has put “Singleton” or some other hint in the class name, and the reader knows design patterns well enough to understand the hint, the code will read as though a new instance is being created and returned.

A third objection is that the Singleton Pattern forces a design commitment that [The Global Object Pattern](https://python-patterns.guide/python/module-globals/) does not. Offering a global object still leaves a programmer free to create other instances of the class — which can be particularly helpful for tests, letting them each test a completely separate object without needing to reset a shared object back to a known good state. But the Singleton Pattern makes additional instances impossible. (Unless the caller is willing to stoop to monkey patching; or temporarily modifying `_instance` to subvert the logic in `__new__()`; or creating a subclass that replaces the method. But a pattern you have to work around is generally a pattern you should avoid.)

Why, then, would you use the Singleton Pattern in Python?

The one situation that would really demand the pattern would be an existing class that, because of a new requirement, will now operate best as a single instance. If it’s not possible to migrate all client code to stop calling the class directly and start using a global object, then the Singeton Pattern would be a natural approach to pivoting to a singleton while preserving the old syntax.

But, otherwise, the pattern is best avoided in favor of following the advice of the [official Python FAQ](https://docs.python.org/3/faq/programming.html#how-do-i-share-global-variables-across-modules) and using the [The Global Object Pattern](https://python-patterns.guide/python/module-globals/).

---

<!-- source: https://python-patterns.guide/gang-of-four/composite/ -->

_A “Structural Pattern” from the_[Gang of Four book](https://python-patterns.guide/gang-of-four/)

Verdict

The Composite Pattern can bring symmetry not only to object hierarchies in Python, but even to hierarchies exposed by low-level system calls and high-level network applications. In Python, the Composite Pattern can often be implemented with less fuss than in tightly constrained object oriented languages. You won’t be forced to inherit your container objects and the objects inside of them from a common parent class. Instead, you can build classes that share only a common interface rather than any implementation — or that are simply duck typed to offer common behavior.

The Composite Pattern suggests that whenever you design “container” objects that collect and organize what we’ll call “content” objects, you will simplify many operations if you give container objects and content objects a shared set of methods and thereby support as many operations as possible without the caller having to care whether they have been passed an individual content object or an entire container.

This is such a general idea that we can begin by stepping back from Python and even from object-based programming, and looking at how the Composite Pattern works at the level of an operating system.

## Example: the UNIX file system[¶](https://python-patterns.guide/gang-of-four/composite/#example-the-unix-file-system "Link to this heading")

The admirably pithy two-letter UNIX command `ls`, according to its manual page, stands for “list directory” and when given the path to a directory will list the files and subdirectories inside.

$ ls /usr
3bnet/       bin/         lbin/        lost+found/  options/     spool/
adm/         gnu/         lib/         mail/        preserve/    src/
admin/       include/     local/       news/        pub/         tmp/

But the name “list directory” is misleadingly narrow, because `ls` is also happy to be given a single file’s path as its argument!

$ ls /usr/bin/banner
/usr/bin/banner

Of course, users rarely invoke `ls` on a single file like this, without specifying any option; the only thing you learn is that the file exists (if it doesn’t, `ls` will complain “No such file or directory”). Its ability to accept single file names makes more sense when combined with its “long listing” option.

$ ls -l /usr/bin/banner
-r-xr-xr-x   1 bin      bin        12620 Mar  3  1988 /usr/bin/banner

This symmetry — that `ls` operates without complaint on both individual files and also on the directories that contain them — seems so natural to most users that you might not notice the powerful design decision behind it. It would have been very easy for an operating system author to provide one command for listing a directory, and an entirely different command to show the attributes of one particular file. But the lack of symmetry would have carried a cost. While exploring the filesystem, you would then have had to constantly remember to switch from one command to the other depending on whether the object of your attention was a directory or file.

Worse yet, two separate commands would have provided no way to support wildcard operations that might match both files and directories. But, happily, `ls` has no problem with a heterogeneous argument list that has both individual files and also a directory inside:

$ ls -C /etc/l*
/etc/labelit    /etc/ldsysdump  /etc/led        /etc/link

/etc/log:
filesave.log

Here, `ls` has transparently detected that four of the names matched by the wildcard `/etc/l*` are files but that `/etc/log` is a directory with more files inside. (Well, with one file inside.) Had UNIX supplied separate commands for listing a file and listing a directory, this wildcard could not safely have been an argument to either command.

This, at the level of a command line interface, is the Composite Pattern. Operations like `ls` and `du` and `chmod` that make sense on both files and directories are implemented so that they run transparently on both. This not only lowers cognitive overhead, but makes shell scripts easier to write — there are many operations that a script can simply run blindly without needing to stop and check first whether a path names a file or a directory.

The art of using the Composite Pattern is determining where to break the symmetry. For example, the UNIX filesystem provides completely different commands `touch` for creating a new file and `mkdir` for creating a new directory. This could instead have been a single command with an option that flipped it from file-creating mode to directory-creating mode. But the designers thought that the two operations were conceptually different enough to deserve separate commands. The decision of how much symmetry to create will weigh upon each operation that a designer implements.

Forcing symmetry where there is really a difference can create awkward special cases. For example, two of the three permission bits in UNIX apply equally to directories and files: `r` gives read permission and `w` gives write permission. But the symmetry breaks at `x`, the third bit, which gives permission to “execute” a file but to “search” a directory by using it in a path. Should there have been two different `chmod` commands, one for files and one for directories? Or should the single `chmod` binary at least have used a different letter for that third bit, maybe `x` when applied to a file but `s` for “search” when applied to a directory? I myself think the designers of UNIX made the right decision here, because I find it easier to remember that `x` means something a little different for a directory than to remember a separate letter for directories, or a separate command. But the decision could have gone either way, and making decisions like these are where the designer applying the Composite Pattern needs finesse.

It should be noted that the symmetries that exist between files and directories on the command line are not exactly the same symmetries that exist down beneath `ls` and `chmod` at the level of system calls. At each level, the Composite Pattern was applied a bit differently. For system calls, some symmetry does exist: `stat()` and `chmod()` and `chown()` operate happily on both files and directories.

But `ls` is hiding the fact that if `stat()` reveals that a path names a directory, then `ls` needs to switch to a directory-specific system call to list the files inside. There is no symmetry between the UNIX system call for reading a normal file’s content and the call for reading the list of files in a directory, and for a crucial reason: the two operations return different types of data. A file contains an unstructured stream of bytes; a directory, a series of distinct filenames. The question of return type will serve as a very important guardrail when you are designing in Python: if your desire to create symmetry between container and content leads you to engineer calls that require an `if` statement or `isinstance()` to safely handle their return value, then the desire for symmetry has led you astray.

## On hierarchies[¶](https://python-patterns.guide/gang-of-four/composite/#on-hierarchies "Link to this heading")

As we now turn our attention to how the Composite Pattern looks in a programming language like Python, we should ponder a question that hangs above so much of the object-oriented and design-pattern literature from the 1990s:

Where have all the hierarchies gone?

The construction and manipulation of extensive hierarchies was both a frequent exercise for new programmers and a tedious labor for more experienced programmers. Hours were spent deciding how hierarchies would be constructed, what operations they would support, and how their destructors could be safely invoked. Hierarchies were everywhere.

And then they began to recede, like a tide that having run far up the sand begins to finally sweep out again.

*   Popular languages in the late 1990s went wild for deeply nested package namespaces. To take a modern example from Go, the package `google.golang.org/appengine`, one must admit, comes with a hard guarantee that it won’t conflict with the name of a package from another firm. The Zope 3 project, in its heyday, happily festooned the Python Package Index with multi-level package names like `zope.app.form` and `zope.app.i18n`. But today most Python packages opt for a simple non-compound name that jostles alongside the names of all other Python packages. And it almost never causes problems.

*   The programming curricula of yore were rife with binary search trees, B+trees, and tree balancing algorithms. But in real code, trees are very scarce. For every programmer who works on trees to, say, to write a persistent storage engine like BoltDB or Redis, a thousand programmers get to skip the exercise. Python programmers don’t tend to use binary search trees; we use the even faster hash table (the Python “dictionary”) whose structure, as it happens, is entirely flat — not a hierarchy.

*   There was an era when hierarchy was inherent in the structure of databases. An employee record might hold a salary history right inside of it. But while hierarchy continues to exist around the edges of data storage, most recently in the form of NoSQL and document databases, our workhorse data stores tend to be flat ones: the relational database, the CSV file, the Pandas dataframe.

Again and again our discipline seems to revert back, where we can, to tables and lists and arrays where hierarchies might have reigned instead. The principle has even been enshrined in the famous _Zen of Python:_

> “Flat is better than nested.”

The big exception, the realm in which hierarchy does reign supreme today, is the document. Documents are almost universally processed and represented as a hierarchy of sections and paragraphs beneath which are spans of bold and italics and hyperlinks. But the whole point of their being documents is that we aren’t always forced to build them in code using object and method calls. Instead, when we can, we parse them from a native representation that makes the hierarchy explicit and natural. The great monument to the Composite Pattern on today’s web is not document construction— documents are usually delivered as HTML— but document manipulation, through the Document Object Model exposed for the use of JavaScript code.

I will leave for another time my discussion of how the Document Object Model delivered a hierarchy, so programmers invented jQuery because they preferred an array instead.

Let’s now turn to what the Composite pattern looks like in code.

## Example: GUI programming with Tkinter[¶](https://python-patterns.guide/gang-of-four/composite/#example-gui-programming-with-tkinter "Link to this heading")

Let’s imagine that we want to print to the screen the hierarchy of frames and buttons out of which we have built a graphical user interface (GUI) using Tkinter, which comes built in to Python.

It would have been easy enough for Tkinter’s designers to have decided that only `Frame` containers needed `winfo_children()` methods to list their children — after all, simpler widgets like `Label` and `Button` aren’t supposed to contain children, and could have omitted the method entirely. But that asymmetry would have forced an `if` statement into any routine that wanted to visit both frames and their children:

# If Frame objects alone had offered winfo_children()

if isinstance(widget, Frame):
    children = widget.winfo_children()
    ...
else:
    # carefully avoid calling winfo_children()
    ...

This pattern, when it can’t be avoided, can at least be improved by dodging the `isinstance()` call and instead using `getattr()` with three arguments to safely examine whether the object has the necessary method. This decouples the code from the vexed question of whether any other Tkinter widgets besides `Frame`, either today or in the future, can also include children widgets inside:

# Improvement: check for methods, not classes
...
winfo_children = getattr(Frame, 'winfo_children', None)
if winfo_children is not None:
    children = winfo_children()
    ...

In either case, the difference between container widgets and normal widgets would have haunted every piece of code that wanted to perform general processing.

But the authors of Tk chose, happily, to implement the Composite Pattern. Instead of making `winfo_children()` a special method that only `Frame` widgets offer, they made it a general method that is available on _every single widget object!_ You never need to check whether it is present. For containers, it returns their list of child widgets. For other widgets? It simply returns an empty list.

Your code can therefore fly forward and always assume the presence of the method. Here, so that you can see a working example, is a complete program that builds a simple Tkinter GUI that can print out the widget hierarchy to the terminal:

from tkinter import Tk, Frame, Button

# Our routine, that gets to treat all widgets the same.

def print_tree(widget, indent=0):
 """Print a hierarchy of Tk widgets in the terminal."""
    print('{:<{}} * {!r}'.format('', indent * 4, widget))
    for child in widget.winfo_children():
        print_tree(child, indent + 1)

# A small sample GUI application with several widgets.

root = Tk()
f = Frame(master=root)
f.pack()

tree_button = Button(f)
tree_button['text'] = 'Print widget tree'
tree_button['command'] = lambda: print_tree(f)
tree_button.pack({'side': 'left'})

quit_button = Button(f)
quit_button['text'] = 'Quit Tk application'
quit_button['command'] =  f.quit
quit_button.pack({'side': 'left'})

f.mainloop()
root.destroy()

The resulting printout looks like:

* <tkinter.Frame object .!frame>
    * <tkinter.Button object .!frame.!button>
    * <tkinter.Button object .!frame.!button2>

Thanks to the Composite Pattern symmetry between widgets, no `if` statement is necessary to handle whatever kind of widget is passed to `print_tree()`.

Note that there is controversy among Composite Pattern enthusiasts over whether all widgets should really act like containers— isn’t it fraudulent, they ask, for a widget to implement `winfo_children()` if it’s not going to let you add child widgets? What sense does it make for it to act like a halfway container that supports read operations (“list children”) without the corresponding write operations (“add child”)? The more restrictive option would be to avoid putting `winfo_children()` on all widgets and instead only making truly general operations like `winfo_rootx()` universal (general, because all widgets have an _x_-coordinate). I myself tend to enjoy interfaces more when there is as much symmetry as possible.

If you study the Tkinter library — which is perhaps the most classic object oriented module in the entire Python Standard Library — you will find several more instances where a method that could have been limited to a few widgets was instead made a common operation on them all for the sake of simplicity and for the convenience of all the code that uses them. This is the Composite Pattern.

## Implementation: to inherit, or not?[¶](https://python-patterns.guide/gang-of-four/composite/#implementation-to-inherit-or-not "Link to this heading")

The benefits of the symmetry that the Composite Pattern creates between containers and their contents only accrue if the symmetry makes the objects interchangeable. But here, some statically typed languages impose an obstacle.

One problem is posed by the most limited of the static languages. In those languages, objects of two different classes are only interchangeable if they are subclasses of a single parent class that implements the methods they have in common — or, if one of the two classes inherits directly from the other.

In static languages that are a bit more powerful, the restriction is gentler. There is no strict need for a container and its contents to share an implementation. As long as both of them conform to an “interface” that declares exactly which methods they implement in common, the objects can be called symmetrically.

In Python, both of these restrictions evaporate! You are free to position your code anywhere along the spectrum of safety versus brevity that you prefer. You can go the classic route and have a common superclass:

class Widget(object):
    def children(self):
        return []

class Frame(Widget):
    def  __init__ (self, child_widgets):
        self.child_widgets = child_widgets

    def children(self):
        return self.child_widgets

class Label(Widget):
    def  __init__ (self, text):
        self.text = text

Or your objects can simply duck type the same interface, and you can rely on tests to help you maintain the symmetries between containers and contents. (Where, for very simple scripts, your “test” might simply be the fact that the code runs.)

class Frame(object):
    def  __init__ (self, child_widgets):
        self.child_widgets = child_widgets

    def children(self):
        return self.child_widgets

class Label(object):
    def  __init__ (self, text):
        self.text = text

    def children(self):
        return []

Or you can choose another point on the design spectrum between these two extremes. Python supports many approaches:

*   The classic common superclass architecture, shown in the first example above.

*   Making the superclass an abstract base class with the tools inside Standard Library’s `abc` module.

*   Having the two classes share an interface, like those supported by the old `zope.interface` package.

*   You could spin up a type checking library like MyPy and use annotations to ask for hard guarantees that all of the objects processed by your code — both container and contents — implement the runtime behaviors that your code requires.

*   You could duck type, and ask for neither permission or forgiveness!

Because Python offers this whole range of approaches, I choose not to define the Composite Pattern classically, where it’s defined as one particular mechanism (a superclass) for creating or enforcing symmetry. Instead, I define it simply as the creation of symmetry — by whatever means — among the objects involved in concentric object hierarchies.

---

<!-- source: https://python-patterns.guide/gang-of-four/decorator-pattern/ -->

_A “Structural Pattern” from the_[Gang of Four book](https://python-patterns.guide/gang-of-four/)

Warning

The “Decorator Pattern” ≠ Python “decorators”!

If you are interested in Python decorators like `@classmethod` and `@contextmanager` and `@wraps()`, then stay tuned for a later phase of this project in which I start tackling Python language features.

Verdict

The Decorator Pattern can be useful in Python code! Happily, the pattern can be easier to implement in a dynamic language like Python than in the static languages where it was first practiced. Use it on the rare occasion when you need to adjust the behavior of an object that you can’t subclass but can only wrap at runtime.

Contents:

*   [The Decorator Pattern](https://python-patterns.guide/gang-of-four/decorator-pattern/#the-decorator-pattern)

    *   [Definition](https://python-patterns.guide/gang-of-four/decorator-pattern/#definition)

    *   [Implementing: Static wrapper](https://python-patterns.guide/gang-of-four/decorator-pattern/#implementing-static-wrapper)

    *   [Implementing: Tactical wrapper](https://python-patterns.guide/gang-of-four/decorator-pattern/#implementing-tactical-wrapper)

    *   [Implementing: Dynamic wrapper](https://python-patterns.guide/gang-of-four/decorator-pattern/#implementing-dynamic-wrapper)

    *   [Caveat: Wrapping doesn’t actually work](https://python-patterns.guide/gang-of-four/decorator-pattern/#caveat-wrapping-doesnt-actually-work)

    *   [Hack: Monkey-patch each object](https://python-patterns.guide/gang-of-four/decorator-pattern/#hack-monkey-patch-each-object)

    *   [Hack: Monkey-patch the class](https://python-patterns.guide/gang-of-four/decorator-pattern/#hack-monkey-patch-the-class)

    *   [Further Reading](https://python-patterns.guide/gang-of-four/decorator-pattern/#further-reading)

The Python core developers made the terminology surrounding this design pattern more confusing than necessary by using the _decorator_ for an entirely [unrelated language feature](https://www.python.org/dev/peps/pep-0318/). The timeline:

*   The design pattern was developed and named in the early 1990s by participants in the “Architecture Handbook” series of workshops that were kicked off at OOPSLA’90, a conference for researchers of object-oriented programming languages.

*   The design pattern became famous as the “Decorator Pattern” with the 1994 publication of the Gang of Four’s _Design Patterns_ book.

*   In 2003, the Python core developers decided to re-use the term _decorator_ for a completely unrelated feature they were adding to Python 2.4.

Why were the Python core developers not more concerned about the name collision? It may simply be that Python’s dynamic features kept its programming community so separate from the world of design-pattern literature for heavyweight languages that the core developers never imagined that confusion could arise.

To try to keep the two concepts straight, I will use the term _decorator class_ instead of just _decorator_ when referring to a class that implements the Decorator Pattern.

## Definition[¶](https://python-patterns.guide/gang-of-four/decorator-pattern/#definition "Link to this heading")

A _decorator_ class:

*   Is an _adapter_ (see the _Adapter Pattern_)

*   That implements the same interface as the object it wraps

*   That delegates method calls to the object it wraps

The decorator class’s purpose is to add to, remove from, or adjust the behaviors that the wrapped object would normally implement when its methods are called. With a decorator class, you might:

*   Log method calls that would normally work silently

*   Perform extra setup or cleanup around a method

*   Pre-process method arguments

*   Post-process return values

*   Forbid actions that the wrapped object would normally allow

These purposes might remind you of situations in which you would also think of subclassing an existing class. But the Decorator Pattern has a crucial advantage over a subclass: you can only solve a problem with a subclass when your own code is in charge of creating the objects in the first place. For example, it isn’t helpful to subclass the Python file object if a library you’re using is returning normal file objects and you have no way to intercept their construction — your new `MyEvenBetterFile` subclass would sit unused. A decorator class does not have that limitation. It can be wrapped around a plain old file object any time you want, without the need for you be in control when the wrapped object was created.

## Implementing: Static wrapper[¶](https://python-patterns.guide/gang-of-four/decorator-pattern/#implementing-static-wrapper "Link to this heading")

First, let’s learn the drudgery of creating the kind of decorator class you would write in C++ or Java. We will not take advantage of the fact that Python is a dynamic language, but will instead write static (non-dynamic) code where every method and attribute appears literally, on the page.

To be complete — to provide a real guarantee that every method called and attribute manipulated on the decorator object will be backed by the real behavior of the adapted object — the decorator class will need to implement:

*   Every method of the adapted class

*   A getter for every attribute

*   A setter for every attribute

*   A deleter for every attribute

This approach is conceptually simple but, wow, it involves a lot of code!

Imagine that one library is giving you open Python file objects, and you need to pass them to another routine or library — but to debug some product issues with latency, you want to log each time that data is written to the file.

Python file objects often seem quite simple. We usually `read()` from them, `write()` to them, and not much else. But in fact the file object supports more than a dozen methods and offers five different attributes! A wrapper class that really wants to implement that full behavior runs to nearly 100 lines of code — as shown here, in our first working example of the Decorator Pattern:

# Traditional Decorator pattern: noticeably verbose

class WriteLoggingFile1(object):
    def  __init__ (self, file, logger):
        self._file = file
        self._logger = logger

    # We need to implement every file method,
    # and in the truly general case would need
    # a getter, setter, and deleter for every
    # single attribute! Here goes:

    def  __enter__ (self):
        return self._file. __enter__ ()

    def  __exit__ (self, *excinfo):
        return self._file. __exit__ (*excinfo)

    def  __iter__ (self):
        return self._file. __iter__ ()

    def  __next__ (self):
        return self._file. __next__ ()

    def  __repr__ (self):
        return self._file. __repr__ ()

    def close(self):
        return self._file.close()

    @property
    def closed(self):
        return self._file.closed

    @closed.setter
    def closed(self, value):
        self._file.closed = value

    @closed.deleter
    def closed(self):
        del self._file.closed

    @property
    def encoding(self):
        return self._file.encoding

    @encoding.setter
    def encoding(self, value):
        self._file.encoding = value

    @encoding.deleter
    def encoding(self):
        del self._file.encoding

    @property
    def errors(self):
        return self._file.errors

    @errors.setter
    def errors(self, value):
        self._file.errors = value

    @errors.deleter
    def errors(self):
        del self._file.errors

    def fileno(self):
        return self._file.fileno()

    def flush(self):
        return self._file.flush()

    def isatty(self):
        return self._file.isatty()

    @property
    def mode(self):
        return self._file.mode

    @mode.setter
    def mode(self, value):
        self._file.mode = value

    @mode.deleter
    def mode(self):
        del self._file.mode

    @property
    def name(self):
        return self._file.name

    @name.setter
    def name(self, value):
        self._file.name = value

    @name.deleter
    def name(self):
        del self._file.name

    @property
    def newlines(self):
        return self._file.newlines

    @newlines.setter
    def newlines(self, value):
        self._file.newlines = value

    @newlines.deleter
    def newlines(self):
        del self._file.newlines

    def read(self, *args):
        return self._file.read(*args)

    def readinto(self, buffer):
        return self._file.readinto(buffer)

    def readline(self, *args):
        return self._file.readline(*args)

    def readlines(self, *args):
        return self._file.readlines(*args)

    def seek(self, *args):
        return self._file.seek(*args)

    def tell(self):
        return self._file.tell()

    def truncate(self, *args):
        return self._file.truncate(*args)

    # Finally, we reach the two methods
    # that we actually want to specialize!
    # These log each time data is written:

    def write(self, s):
        self._file.write(s)
        self._logger.debug('wrote %s bytes to %s', len(s), self._file)

    def writelines(self, strings):
        if self.closed:
            raise ValueError('this file is closed')
        for s in strings:
            self.write(s)

So for the sake of the half-dozen lines of code at the bottom that supplement the behavior of `write()` and `writelines()`, another hundred or so lines of code wound up being necessary.

You will notice that each Python object attribute goads us into being even more verbose than Java! A typical Java attribute is implemented as exactly two methods, like `getEncoding()` and `setEncoding()`. A Python attribute, on the other hand, will in the general case need to be backed by _three_ actions — get, set, and delete — because Python’s object model is dynamic and supports the idea that an attribute might disappear from an instance.

Of course, if the class you are decorating does not have as many methods and attributes as the Python file object we took as our example, then your wrapper will be shorter. But in the general case, writing out a full wrapper class will be tedious unless you have a tool like an IDE that can automate the process. Also, the wrapper will need to be updated in the future if the underlying object gains (or loses) any methods, arguments, or attributes.

## Implementing: Tactical wrapper[¶](https://python-patterns.guide/gang-of-four/decorator-pattern/#implementing-tactical-wrapper "Link to this heading")

The wrapper in the previous section might have struck you as ridiculous. It tackled the Python file object as a general example of a class that needed to be wrapped, instead of studying the how file objects work to look for shortcuts:

*   File objects are implemented in the C language and don’t, in fact, permit deletion of any of their attributes. So our wrapper could have omitted all 6 deleter methods without any consequence, since the default behavior of a property in the absence of a deleter is to disallow deletion anyway. This would have saved 18 lines of code.

*   All file attributes except `mode` are read-only and raise an `AttributeError` if assigned to — which is the behavior if a property lacks a setter method. So 5 of our 6 setters can be omitted, saving 15 more lines of code and bringing our wrapper to ⅓ its original length without sacrificing correctness.

It might also have occurred to you that the code to which you are passing the wrapper is unlikely to call every single file method that exists. What if it only calls two methods? Or only one? In many cases a programmer has found that a trivial wrapper like the following will perfectly satisfy real-world code that just wants to write to a file:

# Tactical version of Decorator Pattern:
# what if you read the code, and the only thing
# the library really needs is the write() method?

class WriteLoggingFile2(object):
    def  __init__ (self, file, logger):
        self._file = file
        self._logger = logger

    def write(self, s):
        self._file.write(s)
        self._logger.debug('wrote %s bytes to %s', len(s), self._file)

Yes, this can admittedly be a bit dangerous. A routine that seems so happy with a minimal wrapper like this can suddenly fail later if rare circumstances make it dig into methods or attributes that you never implemented because you never saw it use them. Even if you audit the library’s code and are sure it can never call any method besides `write()`, that could change the next time you upgrade the library to a new version.

In a more formal programming language, a duck typing requirement like “this function requires a file object” would likely be replaced with an exact specification like “this argument needs to support a `writelines()` method” or “pass an object that offers every methods in the interface `IWritableFile`.” But most Python code lacks this precision and will force you, as the author of a wrapper class, to decide where to draw the line between the magnificent pedantry of wrapping every possible method and the danger of not wrapping enough.

## Implementing: Dynamic wrapper[¶](https://python-patterns.guide/gang-of-four/decorator-pattern/#implementing-dynamic-wrapper "Link to this heading")

A very common approach to the Decorator Pattern in Python is the dynamic wrapper. Instead of trying to implement a method and property for every method and attribute on the wrapped object, a dynamic wrapper intercepts live attribute accesses as the program executes and responds by trying to access the same attribute on the wrapped object.

A dynamic wrapper implements the dunder methods `__getattr__()`, `__setattr__()`, and — if it really wants to be feature-complete — `__delattr__()` and responds to each of them by performing the equivalent operation on the wrapped object. Because `__getattr__()` is only invoked for attributes that are in fact missing on the wrapper, the wrapper is free to offer real implementations of any methods or properties it wants to intercept.

There are a few edge cases that prevent every attribute access from being handled with `__getattr__()`. For example, if the wrapped object is iterable, then the basic operation `iter()` will fail on the wrapper if the wrapper is not given a real `__iter__()` method of its own. Similarly, even if the wrapped object is an iterator, `next()` will fail unless the wrapper offers a real `__next__()`, because these two operations examine an object’s class for dunder methods instead of hitting the object directly with a `__getattr__()`.

As a result of these special cases, a getattr-powered wrapper usually involves at least a half-dozen methods in addition to the methods you specifically want to specialize:

# Dynamic version of Decorator Pattern: intercept live attributes

class WriteLoggingFile3(object):
    def  __init__ (self, file, logger):
        self._file = file
        self._logger = logger

    # The two methods we actually want to specialize,
    # to log each occasion on which data is written.

    def write(self, s):
        self._file.write(s)
        self._logger.debug('wrote %s bytes to %s', len(s), self._file)

    def writelines(self, strings):
        if self.closed:
            raise ValueError('this file is closed')
        for s in strings:
            self.write(s)

    # Two methods we don't actually want to intercept,
    # but iter() and next() will be upset without them.

    def  __iter__ (self):
        return self. __dict__ ['_file']. __iter__ ()

    def  __next__ (self):
        return self. __dict__ ['_file']. __next__ ()

    # Offer every other method and property dynamically.

    def  __getattr__ (self, name):
        return getattr(self. __dict__ ['_file'], name)

    def  __setattr__ (self, name, value):
        if name in ('_file', '_logger'):
            self. __dict__ [name] = value
        else:
            setattr(self. __dict__ ['_file'], name, value)

    def  __delattr__ (self, name):
        delattr(self. __dict__ ['_file'], name)

As you can see, the code can be quite economical compared to the vast slate of methods we saw earlier in `WriteLoggingFile1` for manually implementing every possible attribute.

This extra level of indirection does carry a small performance penalty for every attribute access, but is usually preferred to the burden of writing a static wrapper.

Dynamic wrappers also offer pleasant insulation against changes that might happen in the future to the object being wrapped. If a future version of Python adds or removes an attribute or method from the file object, the code of `WriteLoggingFile3` will require no change at all.

## Caveat: Wrapping doesn’t actually work[¶](https://python-patterns.guide/gang-of-four/decorator-pattern/#caveat-wrapping-doesnt-actually-work "Link to this heading")

If Python didn’t support introspection — if the only operation you could perform on an object was attribute lookup, whether statically through an identifier like `f.write` or dynamically via `getattr(f, attrname)` string lookup — then a decorator could be foolproof. As long as every attribute lookup that succeeds on the wrapped object will return the same sort of value when performed on the wrapper, then other Python code would never know the difference.

But Python is not merely a dynamic programming language; it also supports introspection. And introspection is the downfall of the Decorator Pattern. If the code to which you pass the wrapper decides to look deeper, all kinds of differences become apparent. The native file object, for example, is buttressed with many private methods and attributes:

>>> from logging import getLogger
>>> f = open('/etc/passwd')
>>> dir(f)
['_CHUNK_SIZE', '__class__', '__del__', '__delattr__', '__dict__', '__dir__', '__doc__', '__enter__', '__eq__', '__exit__', '__format__', '__ge__', '__getattribute__', '__getstate__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__iter__', '__le__', '__lt__', '__ne__', '__new__', '__next__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__', '_checkClosed', '_checkReadable', '_checkSeekable', '_checkWritable', '_finalizing', 'buffer', 'close', 'closed', 'detach', 'encoding', 'errors', 'fileno', 'flush', 'isatty', 'line_buffering', 'mode', 'name', 'newlines', 'read', 'readable', 'readline', 'readlines', 'seek', 'seekable', 'tell', 'truncate', 'writable', 'write', 'writelines']

Your wrapper, on the other hand — if you have crafted it around the file’s public interface — will lack all of those private accouterments. Behind your carefully implemented public methods and attributes are the bare dunder methods of a generic Python `object`, plus the few you had to implement to maintain compatibility:

>>> w = WriteLoggingFile1(f, getLogger())
>>> dir(w)
['__class__', '__delattr__', '__dict__', '__dir__', '__doc__', '__enter__', '__eq__', '__exit__', '__format__', '__ge__', '__getattribute__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__iter__', '__le__', '__lt__', '__module__', '__ne__', '__new__', '__next__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__', '__weakref__', '_file', '_logger', 'close', 'closed', 'encoding', 'errors', 'fileno', 'flush', 'isatty', 'mode', 'name', 'newlines', 'read', 'readinto', 'readline', 'readlines', 'seek', 'tell', 'truncate', 'write', 'writelines']

The tactical wrapper, of course, looks spectacularly different than a real file object, because it does not even attempt to provide the full range of methods available on the wrapped object:

>>> w = WriteLoggingFile2(f, getLogger())
>>> dir(w)
['__class__', '__delattr__', '__dict__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__getattribute__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__le__', '__lt__', '__module__', '__ne__', '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__', '__weakref__', '_file', '_logger', 'write']

More interesting is the getattr wrapper. Even though, in practice, it offers access to every attribute and method of the wrapped class, they are completely missing from its `dir()` because each attribute only springs into existence when accessed by name.

>>> w = WriteLoggingFile3(f, getLogger())
>>> dir(w)
['__class__', '__delattr__', '__dict__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__getattr__', '__getattribute__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__iter__', '__le__', '__lt__', '__module__', '__ne__', '__new__', '__next__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__', '__weakref__', '_file', '_logger', 'write', 'writelines']

Could even these differences be ironed out? If you scroll through the many dunder methods in the [Python Data Model](https://docs.python.org/3/reference/datamodel.html), your might be struck by a sudden wild hope when you see the [__dir__ method](https://docs.python.org/3/reference/datamodel.html#object.__dir__) — surely this is the final secret to camouflaging your wrapper?

Alas, it will not be enough. Even if you implement `__dir__()` and forward it through to the wrapped object, Python special-cases the `__dict__` attribute — accessing it always provides direct access to the dictionary that holds a Python class instance’s attributes.

>>> f. __dict__ 
{'mode': 'r'}
>>> w. __dict__ 
{'_file': <_io.TextIOWrapper name='/etc/passwd' mode='r' encoding='UTF-8'>, '_logger': <RootLogger root (WARNING)>}

You might begin to think of even more obscure ways to subvert Python’s introspection — at this point you might already be thinking of `__slots__`, for example — but all roads lead to the same place. However clever and obscure your maneuvers, at least a small chink will still be left in your wrapper’s armor which will allow careful enough introspection to see the difference. Thus we are lead to a conclusion:

Maxim

The Decorator Pattern in Python supports _programming_ — but not _metaprogramming_. Code that is happy to simply access attributes will be happy to accept a Decorator Pattern wrapper instead. But code that indulges in introspection will see the difference.

Among other things, Python code that attempts to list an object’s attributes, examine its `__class__`, or directly access its `__dict__` will see differences between the object it expected and the decorator object you have in fact given it instead. Well-written application code would never do such things, of course — they are necessary only when implementing a developer tool like a framework, test harness, or debugger. But as you don’t always have the option of dealing solely with well-written libraries, be prepared to see and work around any symptoms of intrusive introspection as you deploy the Decorator Pattern.

## Hack: Monkey-patch each object[¶](https://python-patterns.guide/gang-of-four/decorator-pattern/#hack-monkey-patch-each-object "Link to this heading")

There are two final approaches to decoration based on the questionable practice of monkey patching. The first approach takes each object that needs decoration and installs a new method directly on the object, shadowing the official method that remains on the class itself.

If you have ever attempted this maneuver yourself, you might have run aground on the fact that a function installed on a Python object instance does _not_ receive an automatic `self` argument — instead, it sees only the arguments with which it is literally invoked. So a first try at supplementing a file’s `write()` with logging:

>>> def bind_write_method(logger):
...     # Does not work: will not receive `self` argument
...     def write_and_log(self, s):
...         self.write(s)
...         logger.debug('wrote %s bytes to %s', len(s), self._file)
...     return write_and_log

— will die with an error because the new method sees only one argument, not two:

>>> f = open('/dev/null', 'w')
>>> f.write
<built-in method write ...>
>>> f.write = bind_write_method(getLogger())
>>> f.write('Hello, world.')
Traceback (most recent call last):
 ...
TypeError: write_and_log() missing 1 required positional argument: 's'

The quick way to resolve the dilemma is to do the binding yourself, by providing the object instance to the closure that wraps the new method itself:

>>> def bind_write_method(self, logger):
...     def write_and_log(s):
...         write(s)
...         print('wrote {} bytes to {}'.format(len(s), self.name))
...     write = self.write
...     return write_and_log

>>> f = open('/dev/null', 'w')
>>> f.write = bind_write_method(f, getLogger())
>>> f.write('Hello, world.')
wrote 13 bytes to /dev/null

While clunky, this approach does let you update the action of a single method on a single object instance while leaving the entire rest of its behavior alone.

## Hack: Monkey-patch the class[¶](https://python-patterns.guide/gang-of-four/decorator-pattern/#hack-monkey-patch-the-class "Link to this heading")

Another approach you might see in the wild is to create a subclass that has the desired behaviors overridden, and then to surgically change the class of the object instance. This is not, alas, possible in the general case, and in fact fails for our example here because the file class, like all built-in classes, does not permit assignment to its `__class__` attribute:

>>> f = open('/etc/passwd')
>>> class Foo(type(f)):
...     def write_and_log(self, s):
...         self.write(s)
...         logger.debug('wrote %s bytes to %s', len(s), self._file)
...
>>> f. __class__  = Foo
Traceback (most recent call last):
 ...
TypeError: __class__ assignment only supported for heap types or ModuleType subclasses

But in cases where the surgery does work, you will have an object whose behavior is that of your subclass rather than of its original class.

## Further Reading[¶](https://python-patterns.guide/gang-of-four/decorator-pattern/#further-reading "Link to this heading")

*   If dynamic wrappers and monkey patching spur your interest, check out Graham Dumpleton’s [wrapt library](http://wrapt.readthedocs.io/en/latest/quick-start.html), his accompanying series of [blog posts](http://blog.dscpl.com.au/p/decorators-and-monkey-patching.html), and his [monkey patching talk at Kiwi PyCon](https://www.youtube.com/watch?v=GCZmGgtWi3M) that delve deep into the arcane technical details of the practice.

---

<!-- source: https://python-patterns.guide/gang-of-four/flyweight/ -->

_A “Structural Pattern” from the_[Gang of Four book](https://python-patterns.guide/gang-of-four/)

Verdict

Flyweight objects are such a perfect fit for Python that the language itself uses the pattern for such popular values as identifiers, some integers, and Boolean true and false.

A perfect example of the Flyweight Pattern is the Python [`intern()`](https://docs.python.org/3/library/sys.html#sys.intern) function. It’s a builtin in Python 2 which was moved into the [`sys`](https://docs.python.org/3/library/sys.html) module in Python 3. When you pass it a string, it returns an exactly equal string. Its advantage is that it saves space: no matter how many different string objects you pass it for a particular value like `'xyzzy'`, it returns the same `'xyzzy'` object each time.

It’s used internally in Python to save memory. As Python parses your program it’s likely to encounter a given identifier like `range` several times. Instead of storing each of them as a separate string object, it uses `intern()` so that all mentions of `range` in your code can share a single string object in memory that represents them all.

We can see its behavior by computing the string `'python'` two different ways (to make it likely that any given Python implementation will really give us two different strings) and pass them to the intern function:

>>> from sys import intern  # not necessary in Python 2
>>> a = intern('py' + 'thon')
>>> b = intern('PYTHON'.lower())
>>> a
'python'
>>> b
'python'
>>> a is b
True

Strings are natural candidates for the Flyweight Pattern because they have all three of the key properties of a flyweight object:

*   Python strings are immutable, which makes them safe to share. Otherwise a routine that decided to change one of the string’s characters would affect the single copy shared with everyone else.

*   A Python string carries no context about how it is being used. If it needed to maintain a reference back to the list, dictionary, or other object that was using it, then each string could only serve in one context at a time.

*   Strings are important for their value, not their object identity. We compare them with `==` instead of with the `is` keyword. A well-written Python program will not even notice whether the string `"brandon"` used in one place as a directory name and somewhere else as a username are the same object or two different objects.

The Gang of Four describe these same requirements a bit differently when they require that, “Most object state can be made extrinsic.” They imagine starting with an object that’s a mix of what they call “extrinsic” and “intrinsic” state:

a1 = Glyph(width=6, ascent=9, descent=3, x=32, y=8)
a2 = Glyph(width=6, ascent=9, descent=3, x=8, y=60)

Given a typeface and size, each occurrence of a given letter — say, the letter _M_ — will have the same width, the same ascent above the baseline, and the same descent below it. The Gang of Four call these attributes “intrinsic” to what it means to be the letter _M._ But each _M_ on a page will have a different `x` and `y` coordinate; that state is “extrinsic” and varies from one occurrence of the letter to another.

Given an object that mixes intrinsic and extrinsic state, the Gang of Four arrives at the Flyweight by refactoring to separate the two kinds of state:

a = Glyph(width=6, ascent=9, descent=3)
a1 = DrawnGlyph(glyph=a, x=32, y=8)
a2 = DrawnGlyph(glyph=a, x=8, y=60)

Not only can the space savings from the Flyweight Pattern be considerable, but the [original 1990 paper introducing Flyweights](https://www.researchgate.net/profile/Mark_Linton2/publication/220877079_Glyphs_flyweight_objects_for_user_interfaces/links/58adbb6345851503be91e1dc/Glyphs-flyweight-objects-for-user-interfaces.pdf?origin=publication_detail) found that a document editor written using the pattern had considerably simpler code.

## Factory or Constructor[¶](https://python-patterns.guide/gang-of-four/flyweight/#factory-or-constructor "Link to this heading")

The Gang of Four only imagined using a factory function like `intern()` for managing a collection of flyweights, but Python often moves the logic into a class’s constructor instead.

The simplest example in Python is the `bool` type. It has exactly two instances. While they can be accessed through their builtin names `True` and `False`, they are also returned by their class when it is passed an object to test for truthiness or falsehood.

>>> bool(0)
False
>>> bool('')
False
>>> bool(12)
True

Another example is integers. As an implementation detail, the default C language version of Python treats the integers −5 through 256 as flyweights. Those integers are created ahead of time as the interpreter launches, and are returned when an integer with one of those values is needed. Computing any other integer value results in a unique object from each computation.

>>> 1 + 4 is 2 + 3
True
>>> 100 + 400 is 200 + 300
False

There are a few other flyweights hiding in the Standard Library for very common immutable objects, like the empty string and the empty tuple.

>>> str() is ''
True
>>> tuple([]) is ()
True

Note that not every object pre-built by the interpreter qualifies as a flyweight. The `None` object, for example, does not qualify: a class needs more than one instance to be a true Flyweight, but `None` is the only instance of `NoneType`.

## Implementing[¶](https://python-patterns.guide/gang-of-four/flyweight/#implementing "Link to this heading")

The simplest flyweights are allocated ahead of time. A system for assigning letter grades might use flyweights for the grades themselves:

_grades = [letter + suffix
           for letter in 'ABCD'
           for suffix in ('+', '', '-')] + ['F']

def compute_grade(percent):
    percent = max(59, min(99, percent))
    return _grades[(99 - percent) * 3 // 10]

print(compute_grade(55))
print(compute_grade(89))
print(compute_grade(90))

F
B+
A-

Factories that need to build a flyweight population dynamically are more complicated: they’ll need a dynamic data structure in which to enroll the flyweights and find them again later. A dictionary is a typical choice:

_strings = {}

def my_intern(string):
    s = _strings.setdefault(string, string)
    return s

a1 = my_intern('A')
b1 = my_intern('B')
a2 = my_intern('A')

print(a1 is b1)
print(a1 is a2)

False
True

One danger of dynamically allocated flyweights is the possibility of eventually exhausting memory, if the number of possible values is very large and callers might request a large number of unique values over a program’s runtime. In such cases you might consider using a `WeakValueDictionary` from the `weakref` module.

Weak references wouldn’t work in the simple example given above, because `my_intern` uses each interned string not only as a value but also as the corresponding key. But it should work fine in the more common case where the indexes are simple values but the keys are more complicated object instances.

The Gang of Four define the Flyweight Pattern as using a factory function, but Python provides another possibility: a class can implement the pattern right in its constructor, just like `bool()` and `int()`. Rewriting the above example as a class— and, for the sake of example, allocating objects on-demand instead of building them ahead of time — would produce something like:

class Grade(object):
    _instances = {}

    def  __new__ (cls, percent):
        percent = max(50, min(99, percent))
        letter = 'FDCBA'[(percent - 50) // 10]
        self = cls._instances.get(letter)
        if self is None:
            self = cls._instances[letter] = object. __new__ (Grade)
            self.letter = letter
        return self

    def  __repr__ (self):
        return 'Grade {!r}'.format(self.letter)

print(Grade(55), Grade(85), Grade(95), Grade(100))
print(len(Grade._instances))    # number of instances
print(Grade(95) is Grade(100))  # ask for ‘A’ two more times
print(len(Grade._instances))    # number stayed the same?

Grade 'F' Grade 'B' Grade 'A' Grade 'A'
3
True
3

You can see that once a `Grade` object for _A_ has been created, all further requests for it receive the same object; the instances dictionary doesn’t continue to grow.

Note that we don’t define `__init__()` in a class like this whose `__new__()` might return an existing object. That’s because Python always calls `__init__()` on the object received back from `__new__()` (as long as the object is an instance of the class itself), which would be useful the first time we returned a new Flyweight object, but redundant on subsequent occasions when we returned the already-initialized object. So we instead do the work of initialization right in the middle of `__new__()`:

self.letter = letter

Having illustrated the possibility of hiding your Flyweight Pattern factory inside of `__new__()`, I recommend against it because it produces code whose behavior does not match its spelling. When a Python programmer sees `Grade(95)`, they are going to think “new object instance” along with all of the consequences, unless they are in on the secret that `__new__()` has been overridden and unless they always remember that fact when reading code.

A traditional Flyweight Pattern factory function will be less likely to trigger assumptions like “this code is building a new object” and in any case is simpler both to implement and debug.

---

<!-- source: https://python-patterns.guide/gang-of-four/iterator/ -->

_A “Behavioral Pattern” from the_[Gang of Four book](https://python-patterns.guide/gang-of-four/)

Verdict

Python supports the Iterator Pattern at the most fundamental level available to a programming language: it’s built into Python’s syntax.

But to support not only the object-based Iterator Pattern but also its own legacy iteration protocol, Python relegates the actual iteration object protocol to a pair of dunder methods. Instead of calling these directly, programmers are expected to invoke iteration through a pair of builtin functions.

The least expressive computer languages make no attempt to hide the inner workings of their data structures. In those languages, if you want to visit every element in an array, you have to generate the integer indexes yourself.

Code in such languages struggles to stay at the high level of describing programmer intent. Instead, the flow of each thought is interrupted with low-level data structure details. When code can’t abstract away the mechanics of iteration, it becomes more difficult to read; it’s more liable to errors, because the same iteration details need to be repeated over and over; and changing how a data structure is traversed requires finding and changing every place in the code where that data structure is iterated over.

The remedy is encapsulation. The Iterator Pattern proposes that the details about how a data structure is traversed should be moved into an “iterator” object that, from the outside, simply yields one item after another without exposing the internals of how the data structure is designed.

## Iterating with the “for” loop[¶](https://python-patterns.guide/gang-of-four/iterator/#iterating-with-the-for-loop "Link to this heading")

Python’s `for` loop abstracts the Iterator Pattern so thoroughly that most Python programmers are never even aware of the object design pattern that it enacts beneath the surface. The `for` loop performs repeated assignment, running its indented block of code once for each item in the sequence it is iterating over.

some_primes = [2, 3, 5]
for prime in some_primes:
    print(prime)

2
3
5

The above loop has performed a series of three assignment statements `prime = 2`, `prime = 3`, and `prime = 5`, running the indented block of code after each assignment. The block can include the C-style loop control statements `break` to leave the loop early and `continue` to skip back to the top of the loop.

Because `for` is a repeated assignment statement, it has the same flexibility as Python’s normal `=` assignment operator: by listing several names separated by commas, you can upgrade from assigning to a single name to unpacking a whole tuple. This lets you skip a separate unpacking step.

elements = [('H', 1.008), ('He', 4.003), ('Li', 6.94)]

# You’re not limited to a single name like “tup”...
for tup in elements:
    symbol, weight = tup
    print(symbol, weight)

# ...instead, unpack right inside the "for" statement
for symbol, weight in elements:
    print(symbol, weight)

Famously, this can be coupled with the Python dictionary’s `item()` method to easily visit each dictionary key and value without the expense of a key lookup at the top of each loop.

d = {'H': 1.008, 'He': 4.003, 'Li': 6.94}

# You don’t need to...
for symbol in d.keys():
    weight = d[symbol]
    print(symbol, weight)

# ...instead, you can simply:
for symbol, weight in d.items():
    print(symbol, weight)

The `for` loop combines such admirable concision and expressiveness that Python not only supports it as a stand-alone statement, but has incorporated it into four different expressions — Python’s famous “comprehensions” that build lists, sets, dictionaries, and generators directly from inline loops:

[symbol for symbol, weight in d.items() if weight > 5]
{symbol for symbol, weight in d.items() if weight > 5}
{symbol: weight for symbol, weight in d.items() if weight > 5}
list(symbol for symbol, weight in d.items() if weight > 5)

Python’s decision to re-use its `for` statement syntax inside of expressions — instead of going to the trouble of inventing a separate special-purpose syntax for inline iteration — makes the language simpler, easier to learn, and easier to remember.

## The pattern: the iterable and its iterator[¶](https://python-patterns.guide/gang-of-four/iterator/#the-pattern-the-iterable-and-its-iterator "Link to this heading")

Let’s now step behind the `for` loop and learn about the design pattern that powers it. The traditional Iterator Pattern involves three kinds of object.

First, there’s a _container_ object.

Second, the container’s internal logic lets it corral and organize a number of _item_ objects.

Finally, there’s the key to the pattern: instead of the container inventing its own unique method calls for stepping through its items — which would force the programmer to learn a different approach for every container — it offers sequential access to its items through a generic _iterator_ object that implements the exact same interface as the iterator of every other kind of container.

Python provides a pair of builtins that let you step behind the `for` loop and pull the levers of iteration yourself.

*   `iter()` takes a container object as its argument and asks it to build and return a new iterator object. If the argument you pass isn’t actually a container, a `TypeError` is raised: `object is not iterable`.

*   `next()` takes the iterator as its argument and, each time it’s called, returns the next item from the container. Once the container has no more objects to return, the exception `StopIteration` is raised.

To manually reenact the previous section’s first `for` loop, we make a single call to `iter()` followed by four calls to `next()`:

>>> it = iter(some_primes)
>>> it
<list_iterator object at 0x7f072ffdb518>
>>> print(next(it))
2
>>> print(next(it))
3
>>> print(next(it))
5
>>> print(next(it))
Traceback (most recent call last):
 ...
StopIteration

These are precisely the actions that were taken by Python’s `for` loop. Of course, the real `for` loop doesn’t hard-code exactly the right number of `next()` calls like I did here — instead, `for` is implemented as something like the following `while` loop:

it = iter(some_primes)
while True:
    try:
        prime = next(it)
    except StopIteration:
        break
    else:
        print(prime)

2
3
5

My first question when I learned the Iterator Pattern was: why does the iterator need to be a separate object from the container? Why can’t each container simply include a counter inside that reminds it which object to yield next?

The answer is that a single internal counter would work as long as only one `for` loop at a time were ever iterating over a container. But there are many situations where several `for` loops are working on the same container at once. For example, to generate all combinations of two coin flips, a programmer might write concentric loops:

sides = ['heads', 'tails']
for coin1 in sides:
    for coin2 in sides:
        print(coin1, coin2)

heads heads
heads tails
tails heads
tails tails

If the Python list object `sides` had tried to support iteration using only a single internal counter, then the inner `for` loop would have used up all of the items and left the outer `for` loop without any further items to visit. Instead, we are given a separate iterator on each call to `iter()`.

>>> it1 = iter(sides)
>>> it2 = iter(sides)
>>> it1
<list_iterator object at 0x7fa8b8b292b0>
>>> it2
<list_iterator object at 0x7fa8b8b29400>
>>> it1 is it2
False

Not only concentric loops, but multiple threads of control — whether operating system threads or coroutines — also offer plenty of circumstances under which an object might be operated on by several `for` loops at the same time, so each of those `for` loops will also need their own iterator to avoid throwing each other off track.

## A twist: objects which are their own iterator[¶](https://python-patterns.guide/gang-of-four/iterator/#a-twist-objects-which-are-their-own-iterator "Link to this heading")

Each time you pass a normal Python container like a list, set, or dictionary to `iter()`, you receive a new iterator object that starts visiting the container’s items over again from the beginning.

Some Python objects, however, exhibit a different behavior.

The Python file object is a good example. It conveniently yields lines of text when you iterate across it with a `for` loop. But, unlike a list or dictionary, it doesn’t start over again at the first line when traversed with a new `for` loop. Instead, it remembers its previous place in the file and continues yielding lines from where you previously left off.

The fact that a file picks up where it left off can be used to loop over a file in phases. A simple example of a file format that’s composed of different sections is the traditional UNIX mailbox file:

From jdoe@machine.example Fri Nov 21 09:55:06 1997
From: John Doe <jdoe@machine.example>
To: Mary Smith <mary@example.net>
Subject: Saying Hello
Date: Fri, 21 Nov 1997 09:55:06 -0600

This is a message just to say hello.
So, "Hello".

This file needs to be parsed in three phases because each section is delimited by different rules. The initial “envelope line” that starts with the word `From` is always a single standalone line. The header follows, consisting of a series of colon-separated names and values which is terminated by a single blank line. The body comes last and ends at either the next envelope `From` line or the end of the file. Here’s how we might parse the first message from a mailbox file using only `for` loops:

def parse_email(f):
    for line in f:
        envelope = line
        break
    headers = {}
    for line in f:
        if line == '\n':
            break
        name, value = line.split(':', 1)
        headers[name.strip()] = value.lstrip().rstrip('\n')
    body = []
    for line in f:
        if line.startswith('From'):
            break
        body.append(line)
    return envelope, headers, body

This convenient pattern — in which we tackle each section of the file with its own `for` loop that does a `break` once it’s done processing its section — is possible because each time we start up another loop, the file object continues reading from right where we left off.

with open('email.txt') as f:
    envelope, headers, body = parse_email(f)

print(headers['To'])
print(len(body), 'lines')

Mary Smith <mary@example.net>
2 lines

How does the file object subvert normal iteration and preserve state between one `for` loop and the next?

We can see the answer by stepping behind the `for` loop, calling `iter()` ourselves, and examining the result:

>>> f = open('email.txt')
>>> f
<_io.TextIOWrapper name='email.txt' mode='r' encoding='UTF-8'>
>>> it1 = iter(f)
>>> it1
<_io.TextIOWrapper name='email.txt' mode='r' encoding='UTF-8'>
>>> it2 = iter(f)
>>> it2
<_io.TextIOWrapper name='email.txt' mode='r' encoding='UTF-8'>
>>> it1 is it2 is f
True

The file object is taking advantage of a technicality: the rule that `iter()` must return an iterator never says that the iterator can’t be the iterable object itself! Instead of creating a separate iterator object to keep up with which line from the file should be returned next, the file itself serves as its own iterator and yields a single continuous series of lines, delivering the next available line to whichever of possibly many consumers is the first to invoke `next()`.

In the case of the file object, the decision to collapse the iterable and iterator together into a single object is driven by the behavior of the underlying operating system. Not every kind of file, after all, supports rewind and fast forward — Unix terminals and pipes don’t, for example — so the Python file object simply lets the operating system keep up with the current line and never tries to rewind on its own.

But what if you wanted the ability to iterate in separate phases with other kinds of object, and not just files?

For example, what if you pass a plain list of lines to `parse_email()`? Then the routine breaks — because the second and third `for` loops, instead of continuing from where the previous loop stopped, instead start again at the beginning of the list. Among other problems, this prevents the function from finding the email’s body:

with open('email.txt') as f:
    lines = list(f)

envelope, headers, body = parse_email(lines)
print(headers['To'])
print(len(body), 'lines')

Mary Smith <mary@example.net>
0 lines

How can we support gradual iteration over a standard container like a Python list?

The answer is another extension to the traditional Iterator Pattern: in Python, iterators return themselves if passed to `iter()`! This means that iterators themselves can be passed to `for` loops, and lets you write programs that switch back and forth whenever they want between manual single steps with `next()` and automatic iteration with a `for` loop:

it = iter(some_primes)
print(next(it))
for prime in it:
    print(prime)
    break
print(next(it))

2
3
5

Because the above code handles only a single iterator that we requested ourselves with `iter()`, both its manual `next()` calls as well as its `for()` loop are all advancing the same iterator along through the 3 items in the underlying list. The `for` loop works because the iterator object `it` returns itself when asked for its iterator:

>>> it
<list_iterator object at 0x7f4fdce6c5f8>
>>> iter(it)
<list_iterator object at 0x7f4fdce6c5f8>
>>> iter(it) is it
True

So we can successfully use our `parse_email()` routine with a Python list if, instead of passing the underlying list, we instead pass an iterator that we’ve already constructed. With that change, the routine runs as successfully on a list as it originally did on an open file:

with open('email.txt') as f:
    lines = list(f)

it = iter(lines)
envelope, headers, body = parse_email(it)
print(headers['To'])
print(len(body), 'lines')

Mary Smith <mary@example.net>
2 lines

If you ever really do implement a routine like `parse_email()`, it’s better not to make your caller remember to pass an iterator. Instead, have them pass the container and call `iter()` yourself.

## Implementing an Iterable and Iterator[¶](https://python-patterns.guide/gang-of-four/iterator/#implementing-an-iterable-and-iterator "Link to this heading")

How can a class implement the Iterator Pattern and plug in to Python’s native iteration mechanisms `for`, `iter()`, and `next()`?

*   The container must offer an `__iter__()` method that returns an iterator object. Supporting this method makes a container an _iterable_.

*   Each iterator must offer a `__next__()` method (in old Python 2 code, the spelling is `next()` without the dunder) that returns the next item from the container each time it is called. It should raise `StopIterator` when there are no further items.

*   Remember the special case we learned about in the previous section — that some users pass iterators to a `for` loop instead of passing the underlying container? To cover this case, each iterator is also required to offer an `__iter__()` method that simply returns itself.

We can see all of these requirements working together by implementing our own simple iterator!

Note that there is no requirement that the items yielded by `__next__()` be stored as persistent values inside the container, or even exist until `__next__()` is called. This lets us offer a very simple Iterator Pattern example without even implementing storage in the container:

class OddNumbers(object):
    "An iterable object."

    def  __init__ (self, maximum):
        self.maximum = maximum

    def  __iter__ (self):
        return OddIterator(self)

class OddIterator(object):
    "An iterator."

    def  __init__ (self, container):
        self.container = container
        self.n = -1

    def  __next__ (self):
        self.n += 2
        if self.n > self.container.maximum:
            raise StopIteration
        return self.n

    def  __iter__ (self):
        return self

With these three simple methods — one for the container object, and two for its iterator — an `OddNumbers` container is now eligible for full membership in Python’s rich iteration ecosystem. It will work seamlessly with a `for` loop:

numbers = OddNumbers(7)

for n in numbers:
    print(n)

1
3
5
7

And it works with the `iter()` and `next()` builtins.

it = iter(OddNumbers(5))
print(next(it))
print(next(it))

1
3

And it can even dance with the comprehensions!

print(list(numbers))
print(set(n for n in numbers if n > 4))

[1, 3, 5, 7]
{5, 7}

Three simple methods are all that’s needed to unlock access to Python’s syntax-level support for iteration.

---

<!-- source: https://python-patterns.guide/gang-of-four/composition-over-inheritance/ -->

_A principle from the_[Gang of Four book](https://python-patterns.guide/gang-of-four/)

Verdict

In Python as in other programming languages, this grand principle encourages software architects to escape from Object Orientation and enjoy the simpler practices of Object Based programming instead.

This is the second principle propounded by the [Gang of Four book](https://python-patterns.guide/gang-of-four/) at the very beginning, in its “Introduction” chapter. The principle is so important that they display it indented and in italics, like this:

> _Favor object composition over class inheritance._

Let’s take a single design problem and watch how this principle works itself out through several of the classic Gang of Four design patterns. Each design pattern will assemble simple classes, unburdened by inheritance, into an elegant runtime solution.

## Problem: the subclass explosion[¶](https://python-patterns.guide/gang-of-four/composition-over-inheritance/#problem-the-subclass-explosion "Link to this heading")

A crucial weakness of inheritance as a design strategy is that a class often needs to be specialized along several different design axes at once, leading to what the Gang of Four call “a proliferation of classes” in their Bridge chapter and “an explosion of subclasses to support every combination” in their Decorator chapter.

Python’s [logging module](https://docs.python.org/3/library/logging.html) is a good example in the Standard Library itself of a module that follows the Composition Over Inheritance principle, so let’s use logging as our example. Imagine a base logging class that has gradually gained subclasses as developers needed to send log messages to new destinations.

import sys
import syslog

# The initial class.

class Logger(object):
    def  __init__ (self, file):
        self.file = file

    def log(self, message):
        self.file.write(message + '\n')
        self.file.flush()

# Two more classes, that send messages elsewhere.

class SocketLogger(Logger):
    def  __init__ (self, sock):
        self.sock = sock

    def log(self, message):
        self.sock.sendall((message + '\n').encode('ascii'))

class SyslogLogger(Logger):
    def  __init__ (self, priority):
        self.priority = priority

    def log(self, message):
        syslog.syslog(self.priority, message)

The problem arises when this first axis of design is joined by another. Let’s imagine that log messages now need to be filtered — some users only want to see messages with the word “Error” in them, and a developer responds with a new subclass of `Logger`:

# New design direction: filtering messages.

class FilteredLogger(Logger):
    def  __init__ (self, pattern, file):
        self.pattern = pattern
        super(). __init__ (file)

    def log(self, message):
        if self.pattern in message:
            super().log(message)

# It works.

f = FilteredLogger('Error', sys.stdout)
f.log('Ignored: this is not important')
f.log('Error: but you want to see this')

Error: but you want to see this

The trap has now been laid, and will be sprung the moment the application needs to filter messages but write them to a socket instead of a file. None of the existing classes covers that case. If the developer plows on ahead with subclassing and creates a `FilteredSocketLogger` that combines the features of both classes, then the subclass explosion is underway.

Maybe the programmer will get lucky and no further combinations will be needed. But in the general case the application will wind up with 3×2=6 classes:

Logger            FilteredLogger
SocketLogger      FilteredSocketLogger
SyslogLogger      FilteredSyslogLogger

The total number of classes will increase geometrically if _m_ and _n_ both continue to grow. This is the “proliferation of classes” and “explosion of subclasses” that the Gang of Four want to avoid.

The solution is to recognize that a class responsible for both filtering messages and logging messages is too complicated. In modern Object Oriented practice, it would be accused of violating the “Single Responsibility Principle.”

But how can we distribute the two features of message filtering and message output across different classes?

## Solution #1: The Adapter Pattern[¶](https://python-patterns.guide/gang-of-four/composition-over-inheritance/#solution-1-the-adapter-pattern "Link to this heading")

One solution is the Adapter Pattern: to decide that the original logger class doesn’t need to be improved, because any mechanism for outputting messages can be wrapped up to look like the file object that the logger is expecting.

1.   So we keep the original `Logger`.

2.   And we also keep the `FilteredLogger`.

3.   But instead of creating destination-specific subclasses, we adapt each destination to the behavior of a file and then pass the adapter to a `Logger` as its output file.

Here are adapters for each of the other two outputs:

import socket

class FileLikeSocket:
    def  __init__ (self, sock):
        self.sock = sock

    def write(self, message_and_newline):
        self.sock.sendall(message_and_newline.encode('ascii'))

    def flush(self):
        pass

class FileLikeSyslog:
    def  __init__ (self, priority):
        self.priority = priority

    def write(self, message_and_newline):
        message = message_and_newline.rstrip('\n')
        syslog.syslog(self.priority, message)

    def flush(self):
        pass

Python encourages duck typing, so an adapter’s only responsibility is to offer the right methods — our adapters, for example, are exempt from the need to inherit from either the classes they wrap or from the `file` type they are imitating. They are also under no obligation to re-implement the full slate of more than a dozen methods that a real file offers. Just as it’s not important that a duck can walk if all you need is a quack, our adapters only need to implement the two file methods that the `Logger` really uses.

And so the subclass explosion is avoided! Logger objects and adapter objects can be freely mixed and matched at runtime without the need to create any further classes:

sock1, sock2 = socket.socketpair()

fs = FileLikeSocket(sock1)
logger = FilteredLogger('Error', fs)
logger.log('Warning: message number one')
logger.log('Error: message number two')

print('The socket received: %r' % sock2.recv(512))

The socket received: b'Error: message number two\n'

Note that it was only for the sake of example that the `FileLikeSocket` class is written out above — in real life that adapter comes built-in to Python’s Standard Library. Simply call any socket’s [`makefile()`](https://docs.python.org/3/library/socket.html#socket.socket.makefile) method to receive a complete adapter that makes the socket look like a file.

## Solution #2: The Bridge Pattern[¶](https://python-patterns.guide/gang-of-four/composition-over-inheritance/#solution-2-the-bridge-pattern "Link to this heading")

The Bridge Pattern splits a class’s behavior between an outer “abstraction” object that the caller sees and an “implementation” object that’s wrapped inside. We can apply the Bridge Pattern to our logging example if we make the (perhaps slightly arbitrary) decision that filtering belongs out in the “abstraction” class while output belongs in the “implementation” class.

As in the Adapter case, a separate echelon of classes now governs writing. But instead of having to contort our output classes to match the interface of a Python `file` object — which required the awkward maneuver of adding a newline in the logger that sometimes had to be removed again in the adapter — we now get to define the interface of the wrapped class ourselves.

So let’s design the inner “implementation” object to accept a raw message, rather than needing a newline appended, and reduce the interface to only a single method `emit()` instead of also having to support a `flush()` method that was usually a no-op.

# The “abstractions” that callers will see.

class Logger(object):
    def  __init__ (self, handler):
        self.handler = handler

    def log(self, message):
        self.handler.emit(message)

class FilteredLogger(Logger):
    def  __init__ (self, pattern, handler):
        self.pattern = pattern
        super(). __init__ (handler)

    def log(self, message):
        if self.pattern in message:
            super().log(message)

# The “implementations” hidden behind the scenes.

class FileHandler:
    def  __init__ (self, file):
        self.file = file

    def emit(self, message):
        self.file.write(message + '\n')
        self.file.flush()

class SocketHandler:
    def  __init__ (self, sock):
        self.sock = sock

    def emit(self, message):
        self.sock.sendall((message + '\n').encode('ascii'))

class SyslogHandler:
    def  __init__ (self, priority):
        self.priority = priority

    def emit(self, message):
        syslog.syslog(self.priority, message)

Abstraction objects and implementation objects can now be freely combined at runtime:

handler = FileHandler(sys.stdout)
logger = FilteredLogger('Error', handler)

logger.log('Ignored: this will not be logged')
logger.log('Error: this is important')

Error: this is important

This presents more symmetry than the Adapter. Instead of file output being native to the `Logger` but non-file output requiring an additional class, a functioning logger is now always built by composing an abstraction with an implementation.

Once again, the subclass explosion is avoided because two kinds of class are composed together at runtime without requiring either class to be extended.

## Solution #3: The Decorator Pattern[¶](https://python-patterns.guide/gang-of-four/composition-over-inheritance/#solution-3-the-decorator-pattern "Link to this heading")

What if we wanted to apply two different filters to the same log? Neither of the above solutions supports multiple filters — say, one filtering by priority and the other matching a keyword.

Look back at the filters defined in the previous section. The reason we cannot stack two filters is that there’s an asymmetry between the interface they offer and the interface they wrap: they offer a `log()` method but call their handler’s `emit()` method. Wrapping one filter in another would result in an `AttributeError` when the outer filter tried to call the inner filter’s `emit()`.

If we instead pivot our filters and handlers to offering the same interface, so that they all alike offer a `log()` method, then we have arrived at the Decorator Pattern:

# The loggers all perform real output.

class FileLogger:
    def  __init__ (self, file):
        self.file = file

    def log(self, message):
        self.file.write(message + '\n')
        self.file.flush()

class SocketLogger:
    def  __init__ (self, sock):
        self.sock = sock

    def log(self, message):
        self.sock.sendall((message + '\n').encode('ascii'))

class SyslogLogger:
    def  __init__ (self, priority):
        self.priority = priority

    def log(self, message):
        syslog.syslog(self.priority, message)

# The filter calls the same method it offers.

class LogFilter:
    def  __init__ (self, pattern, logger):
        self.pattern = pattern
        self.logger = logger

    def log(self, message):
        if self.pattern in message:
            self.logger.log(message)

For the first time, the filtering code has moved outside of any particular logger class. Instead, it’s now a stand-alone feature that can be wrapped around any logger we want.

As with our first two solutions, filtering can be combined with output at runtime without building any special combined classes:

log1 = FileLogger(sys.stdout)
log2 = LogFilter('Error', log1)

log1.log('Noisy: this logger always produces output')

log2.log('Ignored: this will be filtered out')
log2.log('Error: this is important and gets printed')

Noisy: this logger always produces output
Error: this is important and gets printed

And because Decorator classes are symmetric — they offer exactly the same interface they wrap — we can now stack several different filters atop the same log!

log3 = LogFilter('severe', log2)

log3.log('Error: this is bad, but not that bad')
log3.log('Error: this is pretty severe')

Error: this is pretty severe

But note the one place where the symmetry of this design breaks down: while filters can be stacked, output routines cannot be combined or stacked. Log messages can still only be written to one output.

## Solution #4: Beyond the Gang of Four patterns[¶](https://python-patterns.guide/gang-of-four/composition-over-inheritance/#solution-4-beyond-the-gang-of-four-patterns "Link to this heading")

Python’s logging module wanted even more flexibility: not only to support multiple filters, but to support multiple outputs for a single stream of log messages. Based on the design of logging modules in other languages — see [PEP 282](https://www.python.org/dev/peps/pep-0282/)’s “Influences” section for the main inspirations — the Python logging module implements its own Composition Over Inheritance pattern.

1.   The `Logger` class that callers interact with doesn’t itself implement either filtering or output. Instead, it maintains a list of filters and a list of handlers.

2.   For each log message, the logger calls each of its filters. The message is discarded if any filter rejects it.

3.   For each log message that’s accepted by all the filters, the logger loops over its output handlers and asks every one of them to `emit()` the message.

Or, at least, that’s the core of the idea. The Standard Library’s logging is in fact more complicated. For example, each handler can carry its own list of filters in addition to those listed by its logger. And each handler also specifies a minimum message “level” like `INFO` or `WARN` that, rather confusingly, is enforced neither by the handler itself nor by any of the handler’s filters, but instead by an `if` statement buried deep inside the logger where it loops over the handlers. The total design is thus a bit of a mess.

But we can use the Standard Library logger’s basic insight — that a logger’s messages might deserve both multiple filters _and_ multiple outputs — to decouple filter classes and handler classes entirely:

# There is now only one logger.

class Logger:
    def  __init__ (self, filters, handlers):
        self.filters = filters
        self.handlers = handlers

    def log(self, message):
        if all(f.match(message) for f in self.filters):
            for h in self.handlers:
                h.emit(message)

# Filters now know only about strings!

class TextFilter:
    def  __init__ (self, pattern):
        self.pattern = pattern

    def match(self, text):
        return self.pattern in text

# Handlers look like “loggers” did in the previous solution.

class FileHandler:
    def  __init__ (self, file):
        self.file = file

    def emit(self, message):
        self.file.write(message + '\n')
        self.file.flush()

class SocketHandler:
    def  __init__ (self, sock):
        self.sock = sock

    def emit(self, message):
        self.sock.sendall((message + '\n').encode('ascii'))

class SyslogHandler:
    def  __init__ (self, priority):
        self.priority = priority

    def emit(self, message):
        syslog.syslog(self.priority, message)

Note that only with this final pivot in our design do filters really shine forth with the simplicity they deserve. For the first time, they accept only a string and return only a verdict. All of the previous designs either hid filtering inside one of the logging classes itself, or saddled filters with additional duties beyond simply rendering a verdict.

In fact, the word “log” has dropped entirely away from the name of the filter class, and for a very important reason: there’s no longer anything about it that’s specific to logging! The `TextFilter` is now entirely reusable in any context that happens to involve strings. Finally decoupled from the specific concept of logging, it will be easier to test and maintain.

Again, as with all Composition Over Inheritance solutions to a problem, classes are composed at runtime without needing any inheritance:

f = TextFilter('Error')
h = FileHandler(sys.stdout)
logger = Logger([f], [h])

logger.log('Ignored: this will not be logged')
logger.log('Error: this is important')

Error: this is important

There’s a crucial lesson here: design principles like Composition Over Inheritance are, in the end, more important than individual patterns like the Adapter or Decorator. Always follow the principle. But don’t always feel constrained to choose a pattern from an official list. The design at which we’ve now arrived is both more flexible and easier to maintain than any of the previous designs, even though they were based on official Gang of Four patterns but this final design is not. Sometimes, yes, you will find an existing Design Pattern that’s a perfect fit for your problem — but if not, your design might be stronger if you move beyond them.

## Dodge: “if” statements[¶](https://python-patterns.guide/gang-of-four/composition-over-inheritance/#dodge-if-statements "Link to this heading")

I suspect that the above code has startled many readers. To a typical Python programmer, such heavy use of classes might look entirely contrived — an awkward exercise in trying to make old ideas from the 1980s seem relevant to modern Python.

When a new design requirement appears, does the typical Python programmer really go write a new class? No! “Simple is better than complex.” Why add a class, when an `if` statement will work instead? A single logger class can gradually accrete conditionals until it handles all the same cases as our previous examples:

# Each new feature as an “if” statement.

class Logger:
    def  __init__ (self, pattern=None, file=None, sock=None, priority=None):
        self.pattern = pattern
        self.file = file
        self.sock = sock
        self.priority = priority

    def log(self, message):
        if self.pattern is not None:
            if self.pattern not in message:
                return
        if self.file is not None:
            self.file.write(message + '\n')
            self.file.flush()
        if self.sock is not None:
            self.sock.sendall((message + '\n').encode('ascii'))
        if self.priority is not None:
            syslog.syslog(self.priority, message)

# Works just fine.

logger = Logger(pattern='Error', file=sys.stdout)

logger.log('Warning: not that important')
logger.log('Error: this is important')

Error: this is important

You may recognize this example as more typical of the Python design practices you’ve encountered in real applications.

The `if` statement approach is not entirely without benefit. This class’s whole range of possible behaviors can be grasped in a single reading of the code from top to bottom. The parameter list might look verbose but, thanks to Python’s optional keyword arguments, most calls to the class won’t need to provide all four arguments.

(It’s true that this class can handle only one file and one socket, but that’s an incidental simplification for the sake of readability. We could easily pivot the `file` and `socket` parameters to lists named `files` and `sockets`.)

Given that every Python programmer learns `if` quickly, but can take much longer to understand classes, it might seem a clear win for code to rely on the simplest possible mechanism that will get a feature working. But let’s balance that temptation by making explicit what’s been lost by dodging Composition Over Inheritance:

1.   **Locality.** Reorganizing the code to use `if` statements hasn’t been an unmitigated win for readability. If you are tasked with improving or debugging one particular feature — say, the support for writing to a socket — you will find that you can’t read its code all in one place. The code behind that single feature is scattered between the initializer’s parameter list, the initializer’s code, and the `log()` method itself.

2.   **Deletability.** An underappreciated property of good design is that it makes deleting features easy. Perhaps only veterans of large and mature Python applications will strongly enough appreciate the importance of code deletion to a project’s health. In the case of our class-based solutions, we can trivially delete a feature like logging to a socket by removing the `SocketHandler` class and its unit tests once the application no longer needs it. By contrast, deleting the socket feature from the forest of `if` statements not only requires caution to avoid breaking adjacent code, but raises the awkward question of what to do with the `socket` parameter in the initializer. Can it be removed? Not if we need to keep the list of positional parameters consistent — we would need to retain the parameter, but raise an exception if it’s ever used.

3.   **Dead code analysis.** Related to the previous point is the fact that when we use Composition Over Inheritance, dead code analyzers can trivially detect when the last use of `SocketHandler` in the codebase disappears. But dead code analysis is often helpless to make a determination like “you can now remove all the attributes and `if` statements related to socket output, because no surviving call to the initializer passes anything for `socket` other than `None`.”

4.   **Testing.** One of the strongest signals about code health that our tests provide is how many lines of irrelevant code have to run before reaching the line under test. Testing a feature like logging to a socket is easy if the test can simply spin up a `SocketHandler` instance, pass it a live socket, and ask it to `emit()` a message. No code runs except code relevant to the feature. But testing socket logging in our forest of `if` statements will run at least three times the number of lines of code. Having to set up a logger with the right combination of several features merely to test one of them is an important warning sign, that might seem trivial in this small example but becomes crucial as a system grows larger.

5.   **Efficiency.** I’m deliberately putting this point last, because readability and maintainability are generally more important concerns. But the design problems with the forest of `if` statements are also signalled by the approach’s inefficiency. Even if you want a simple unfiltered log to a single file, every single message will be forced to run an `if` statement against every possible feature you could have enabled. The technique of composition, by contrast, only runs code for the features you’ve composed together.

For all of these reasons, I suggest that the apparent simplicity of the `if` statement forest is, from the point of view of software design, largely an illusion. The ability to read the logger top-to-bottom as a single piece of code comes at the cost of several other kinds of conceptual expense that will grow sharply with the size of the codebase.

## Dodge: Multiple Inheritance[¶](https://python-patterns.guide/gang-of-four/composition-over-inheritance/#dodge-multiple-inheritance "Link to this heading")

Some Python projects fall short of practicing Composition Over Inheritance because they are tempted to dodge the principle by means of a controversial feature of the Python language: multiple inheritance.

Let’s return to the example code we started with, where `FilteredLogger` and `SocketLogger` were two different subclasses of a base `Logger` class. In a language that only supported single inheritance, a `FilteredSocketLogger` would have to choose to inherit either from `SocketLogger` or `FilteredLogger`, and would then have to duplicate code from the other class.

But Python supports multiple inheritance, so the new `FilteredSocketLogger` can list both `SocketLogger` and `FilteredLogger` as base classes and inherit from both:

# Our original example’s base class and subclasses.

class Logger(object):
    def  __init__ (self, file):
        self.file = file

    def log(self, message):
        self.file.write(message + '\n')
        self.file.flush()

class SocketLogger(Logger):
    def  __init__ (self, sock):
        self.sock = sock

    def log(self, message):
        self.sock.sendall((message + '\n').encode('ascii'))

class FilteredLogger(Logger):
    def  __init__ (self, pattern, file):
        self.pattern = pattern
        super(). __init__ (file)

    def log(self, message):
        if self.pattern in message:
            super().log(message)

# A class derived through multiple inheritance.

class FilteredSocketLogger(FilteredLogger, SocketLogger):
    def  __init__ (self, pattern, sock):
        FilteredLogger. __init__ (self, pattern, None)
        SocketLogger. __init__ (self, sock)

# Works just fine.

logger = FilteredSocketLogger('Error', sock1)
logger.log('Warning: not that important')
logger.log('Error: this is important')

print('The socket received: %r' % sock2.recv(512))

The socket received: b'Error: this is important\n'

This bears several striking resemblances to our Decorator Pattern solution. In both cases:

*   There’s a logger class for each kind of output (instead of our Adapter’s asymmetry between writing files directly but non-files through an adapter).

*   The `message` preserves the exact value provided by the caller (instead of our Adapter’s habit of replacing it with a file-specific value by appending a newline).

*   The filter and loggers are symmetric in that they both implement the same method `log()`. (Our other solutions besides the Decorator had filter classes offering one method and output classes offering another).

*   The filter never tries to produce output on its own but, if a message survives filtering, defers the task of output to other code.

These close similarities with our earlier Decorator solution mean that we can compare it with this new code to make an unusually sharp comparison between Composition Over Inheritance and multiple inheritance. Let’s sharpen the focus still further with a question:

_If we have thorough unit tests for both the logger and filter, how confident are we that they will work together?_

1.   The success of the Decorator example depends only on the public behaviors of each class: that the `LogFilter` offers a `log()` method that in turn calls `log()` on the object it wraps (which a test can trivially verify using a tiny fake logger), and that each logger offers a working `log()` method. As long as our unit tests verify these two public behaviors, we can’t break composition without failing our unit tests.

Multiple inheritance, by contrast, depends on behavior that cannot be verified by simply instantiating the classes in question. The public behavior of a `FilteredLogger` is that it offers a `log()` method that both filters and writes to a file. But multiple inheritance doesn’t merely depend on that public behavior, but on how that behavior is implemented internally. Multiple inheritance will work if the method is deferring to its base class using `super()`, but not if the method does its own `write()` to the file, even though either implementation would satisfy the unit test.

A test suite must therefore go beyond unit testing and perform actual multiple inheritance on the class — or else monkey patch to verify that `log()` calls `super().log()` — to guarantee that multiple inheritance keeps working as future developers work on the code.

2.   Multiple inheritance has introduced a new `__init__()` method because neither base class’s `__init__()` method accepts enough arguments for a combined filter and logger. That new code needs to be tested, so at least one test will be necessary for every new subclass.

You might be tempted to concoct a scheme to avoid a new `__init__()` for every subclass, like accepting `*args` and then passing them on to `super().__init__()`. (If you do pursue that approach, review the classic essay “[Python’s Super Considered Harmful](https://fuhm.net/super-harmful/)” which argues that only `**kw` is in fact safe.) The problem with such a scheme is that it hurts readability — you can no longer figure out what arguments an `__init__()` method takes simply by reading its parameter list. And type checking tools will no longer be able to guarantee correctness.

But whether you give each derived class its own `__init__()` or design them to chain together, your unit tests of the original `FilteredLogger` and `SocketLogger` can’t by themselves guarantee that the classes initialize correctly when combined.

By contrast, the Decorator’s design leaves its initializers happily and strictly orthogonal. The filter accepts its `pattern`, the logger accepts its `sock`, and there is no possible conflict between the two.

3.   Finally, it’s possible that two classes work fine on their own, but have class or instance attributes with the same name that will collide when the classes are combined through multiple inheritance.

Yes, our small examples here make the chance of collision look too small to worry about — but remember that these examples are merely standing in for the vastly more complicated classes you might write in real applications.

Whether the programmer writes tests to guard against collision by running `dir()` on instances of each class and checking for attributes they have in common, or by writing an integration test for every possible subclass, the original unit tests of the two separate classes will once again have failed to guarantee that they can combine cleanly through multiple inheritance.

For any of these reasons, the unit tests of two base classes can stay green even as their ability to be combined through multiple inheritance is broken. This means that the Gang of Four’s “explosion of subclasses to support every combination” will also afflict your tests. Only by testing every combination of _m_×_n_ base classes in your application can you make it safe for the application to use such classes at runtime.

In addition to breaking the guarantees of unit testing, multiple inheritance involves at least three further liabilities.

1.   Introspection is simple in the Decorator case. Simply `print(my_filter.logger)` or view that attribute in a debugger to see what sort of output logger is attached. In the case of multiple inheritance, however, you can only learn which filter and logger have been combined by examining the metadata of the class itself — either by reading its `__mro__` or subjecting the object to a series of `isinstance()` tests.

2.   It’s trivial in the Decorator case to take a live combination of a filter and logger and at runtime to swap in a different logger through assignment to the `.logger` attribute — say, because the user has just toggled a preference in the application’s interface. But to do the same in the multiple inheritance case would require the rather more objectionable maneuver of overwriting the object’s class. While changing an object’s class at runtime is not impossible in a dynamic language like Python, it’s generally considered a symptom that software design has gone wrong.

3.   Finally, multiple inheritance provides no built-in mechanism to help the programmer order the base classes correctly. The `FilteredSocketLogger` won’t successfully write to a socket if its base classes are swapped and, as dozens of Stack Overflow questions attest, Python programmers have perpetual difficultly with putting third-party base classes in the right order. The Decorator pattern, by contrast, makes it obvious which way the classes compose: the filter’s `__init__()` wants a `logger` object, but the logger’s `__init__()` doesn’t ask for a `filter`.

Multiple inheritance, then, incurs a number of liabilities without adding a single advantage. At least in this example, solving a design problem with inheritance is strictly worse than a design based on composition.

## Dodge: Mixins[¶](https://python-patterns.guide/gang-of-four/composition-over-inheritance/#dodge-mixins "Link to this heading")

The `FilteredSocketLogger` in the previous section needed its own custom `__init__()` method because it needed to accept arguments for both of its base classes. But it turns out that this liability can be avoided. Of course, in cases where a subclass doesn’t require any extra data, the problem doesn’t arise. But even classes that do require extra data can have it delivered by other means.

We can make the `FilteredLogger` more friendly to multiple inheritance if we provide a default value for `pattern` in the class itself and then invite callers to customize the attribute directly, out-of-band of initialization:

# Don’t accept a “pattern” during initialization.

class FilteredLogger(Logger):
    pattern = ''

    def log(self, message):
        if self.pattern in message:
            super().log(message)

# Multiple inheritance is now simpler.

class FilteredSocketLogger(FilteredLogger, SocketLogger):
    pass  # This subclass needs no extra code!

# The caller can just set “pattern” directly.

logger = FilteredSocketLogger(sock1)
logger.pattern = 'Error'

# Works just fine.

logger.log('Warning: not that important')
logger.log('Error: this is important')

print('The socket received: %r' % sock2.recv(512))

The socket received: b'Error: this is important\n'

Having pivoted the `FilteredLogger` to an initialization maneuver that’s orthogonal to that of its base class, why not push the idea of orthogonality to its logical conclusion? We can convert the `FilteredLogger` to a “mixin” that lives entirely outside the class hierarchy with which multiple inheritance will combine it.

# Simplify the filter by making it a mixin.

class FilterMixin:  # No base class!
    pattern = ''

    def log(self, message):
        if self.pattern in message:
            super().log(message)

# Multiple inheritance looks the same as above.

class FilteredLogger(FilterMixin, FileLogger):
    pass  # Again, the subclass needs no extra code.

# Works just fine.

logger = FilteredLogger(sys.stdout)
logger.pattern = 'Error'
logger.log('Warning: not that important')
logger.log('Error: this is important')

Error: this is important

The mixin is conceptually simpler than the filtered subclass we saw in the last section: it has no base class that might complicate method resolution order, so `super()` will always call the next base class listed in the `class` statement.

A mixin also has a simpler testing story than the equivalent subclass. Whereas the `FilteredLogger` would need tests that both run it standalone and also combine it with other classes, the `FilterMixin` only needs tests that combine it with a logger. Because the mixin is by itself incomplete, a test can’t even be written that runs it standalone.

But all the other liabilities of multiple inheritance still apply. So while the mixin pattern does improve the readability and conceptual simplicity of multiple inheritance, it’s not a complete solution for its problems.

## Dodge: Building classes dynamically[¶](https://python-patterns.guide/gang-of-four/composition-over-inheritance/#dodge-building-classes-dynamically "Link to this heading")

As we saw in the previous two sections, neither traditional multiple inheritance nor mixins solve the Gang of Four’s problem of “an explosion of subclasses to support every combination” — they merely avoid code duplication when two classes need to be combined.

Multiple inheritance still requires, in the general case, “a proliferation of classes” with _m_×_n_ class statements that each look like:

class FilteredSocketLogger(FilteredLogger, SocketLogger):
    ...

But it turns out that Python offers a workaround.

Imagine that our application reads a configuration file to learn the log filter and log destination it should use, a file whose contents aren’t known until runtime. Instead of building all _m_×_n_ possible classes ahead of time and then selecting the right one, we can wait and take advantage of the fact that Python not only supports the `class` statement but a builtin `type()` function that creates new classes dynamically at runtime:

# Imagine 2 filtered loggers and 3 output loggers.

filters = {
    'pattern': PatternFilteredLog,
    'severity': SeverityFilteredLog,
}
outputs = {
    'file': FileLog,
    'socket': SocketLog,
    'syslog': SyslogLog,
}

# Select the two classes we want to combine.

with open('config') as f:
    filter_name, output_name = f.read().split()

filter_cls = filters[filter_name]
output_cls = outputs[output_name]

# Build a new derived class (!)

name = filter_name.title() + output_name.title() + 'Log'
cls = type(name, (filter_cls, output_cls), {})

# Call it as usual to produce an instance.

logger = cls(...)

The tuple of classes passed to `type()` has the same meaning as the series of base classes in a `class` statement. The `type()` call above creates a new class through multiple inheritance from both a filtered logger and an output logger.

Before you ask: yes, it would also work to build a `class` statement as plain text and then pass it to `eval()`.

But building classes on-the-fly carries severe liabilities.

*   Readability suffers. A human reading the above snippet of code will have to do extra work to determine what sort of object an instance of `cls` is. Also, many Python programmers aren’t familiar with `type()` and will need to stop and puzzle over its documentation. If they have difficulty with the novel concept that classes can be defined dynamically, they might still be confused.

*   If a constructed class like `PatternFilteredFileLog` is named in an exception or error message, the developer will probably be unhappy to discover that nothing comes up when they search the code for that class name. Debugging becomes more difficult when you cannot even locate a class. Considerable time may be spent searching the codebase for `type()` calls and trying to determine which one generated the class. Sometimes developers have to resort to calling each method with bad arguments and using the line numbers in the resulting tracebacks to track down the base classes.

*   Type introspection will, in the general case, fail for classes constructed dynamically at runtime. “Jump to class” shortcuts in your editor won’t have anywhere to take you when you highlight an instance of `PatternFilteredFileLog` in the debugger. And type checking engines like [mypy](https://github.com/python/mypy) and [pyre-check](https://github.com/facebook/pyre-check) will be unlikely to offer the strong protections for your generated class that they’re able to provide for normal Python classes.

*   The beautiful Jupyter Notebook feature `%autoreload` possesses a nearly preternatural ability to detect and reload modified source code in a live Python interpreter. But it’s foiled, for example, by the multiple inheritance classes that [matplotlib builds at runtime](https://github.com/matplotlib/matplotlib/blob/54b426397c0e7567edaee4f7f77036c2b8569573/lib/matplotlib/axes/_subplots.py#L180) through `type()` calls inside its `subplot_class_factory()`.

Once its liabilities are weighed, the attempt to use runtime class generation as a last-ditch maneuver to rescue the already faulty mechanism of multiple inheritance stands as a _reductio ad absurdum_ of the entire project of dodging Composition Over Inheritance when you need an object’s behavior to vary over several independent axes.

---

<!-- source: https://python-patterns.guide/fowler-refactoring/ -->

Martin Fowler’s _Refactoring: Improving the Design of Existing Code_ is more heavy focused on object oriented programming than will typically be useful for a Python codebase, but it is still valuable for its practical approach to code. Instead of comparing grand high-level architectures, its habit is to explain a pattern by starting down in the weeds of a tangled example and then finding an incremental way forward that keeps the code running while making stepwise improvements to its organization.

The [The Null Object Pattern](https://python-patterns.guide/python/sentinel-object/#null-object) is the only one to which this Python Patterns site so far makes reference, but the book can still be recommended as a solid classic that has helped many readers get traction with an existing codebase and develop habits that makes even their own code easier to maintain and understand.
