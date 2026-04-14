# Code Style Guide

This document provides guidelines for project coding style and conventions.

## Table of Contents

- [Line Length & Splitting](#line-length--splitting)
  - [Alignment of Method Signatures](#alignment-of-method-signatures)
  - [Alignment of Function Calls](#alignment-of-function-calls)
  - [Alignment of Log Messages](#alignment-of-log-messages)
  - [Alignment of Assert Statements](#alignment-of-assert-statements)
  - [Multi-line Strings](#multi-line-strings)
- [Whitespace & Formatting](#whitespace--formatting)
  - [Quotes](#quotes)
  - [Spaces Around Operators](#spaces-around-operators)
  - [Blank Lines Between Methods](#blank-lines-between-methods)
  - [Blank Line After Docstring](#blank-line-after-docstring)
  - [Trailing Spaces and Newlines](#trailing-spaces-and-newlines)
  - [Dictionary Format](#dictionary-format)
- [Exception Handling](#exception-handling)
  - [Exception Handling Approach](#exception-handling-approach)
  - [Exception Re-raise Rules](#exception-re-raise-rules)
  - [Bug Sentinel Errors](#bug-sentinel-errors)
  - [Exception Handling Formatting](#exception-handling-formatting)
- [Documentation](#documentation)
  - [Docstrings Style](#docstrings-style)
  - [Documenting Exceptions in Docstrings](#documenting-exceptions-in-docstrings)
  - [Docstring Continuation Line Alignment](#docstring-continuation-line-alignment)
  - [Imperative Voice](#imperative-voice)
  - [Comment Punctuation](#comment-punctuation)
  - [Messages](#messages)
    - [Small vs Capital Letters in Messages](#small-vs-capital-letters-in-messages)
- [Markdown Documentation](#markdown-documentation)
  - [Backtick Usage](#backtick-usage)
  - [Backtick Span Wrapping](#backtick-span-wrapping)
  - [Link Wrapping](#link-wrapping)
- [Code Organization](#code-organization)
  - [Class Layout](#class-layout)
  - [Private vs Public Symbols](#private-vs-public-symbols)
  - [Import Statements](#import-statements)
- [Type Annotations & Type System](#type-annotations--type-system)
  - [Return Type Annotations](#return-type-annotations)
  - [Guarding Typing Imports with TYPE_CHECKING](#guarding-typing-imports-with-type_checking)
  - [Using TypedDict](#using-typeddict)
- [API Design & Conventions](#api-design--conventions)
  - [Prefer Immutable Collections](#prefer-immutable-collections)
  - [Avoid None as Default Value](#avoid-none-as-default-value)
  - [Converting from str to int/float](#converting-from-str-to-intfloat)
  - [Using Keyword Arguments](#using-keyword-arguments)
  - [Exiting the Process](#exiting-the-process)
  - [Paths: pathlib vs os](#paths-pathlib-vs-os)
  - [Avoid next() on Generators](#avoid-next-on-generators)
  - [Using ClassHelpers.close()](#using-classhelpersclose)

## Line Length & Splitting

### Alignment of Method Signatures

If the entire signature fits on one line within the 100-character limit, keep it on one line.

If the signature must be split, use one parameter per line. Do not put multiple parameters on the
same line.

**Alignment Rule**: Use the opening parenthesis `(` as the anchor point.

- The first parameter starts immediately after the `(`
- All subsequent parameters must align vertically at the same column position (column of `(` + 1)
- Each parameter goes on its own line

**Examples:**

```python
# Good: All parameters fit on one line.
def short_func(param1: int, param2: str) -> bool:

# Good: Split with one parameter per line.
def long_function_name(self,
                       param1: int,
                       param2: str,
                       param3: bool = False) -> dict:

# Bad: Multiple parameters on one line when split.
def long_function_name(self, param1: int,
                       param2: str, param3: bool = False) -> dict:

# Bad: Incorrect alignment.
def long_function_name(self,
                    param1: int,
                    param2: str,
                    param3: bool = False) -> dict:
```

If the return type annotation is long, move it to the next line using a backslash `\` continuation.
Align the return type at a 4-character boundary so it ends near the 100-character line limit.

```python
    def read_multiple_features(self,
                               fnames: Sequence[str],
                               cpus: Sequence[int]) -> \
                                    Generator[tuple[int, dict[str, FeatureValueType]], None, None]:
```

### Alignment of Function Calls

When a function or method call does not fit on a single line, split it across multiple lines
following the same alignment rules as method signatures.

Fit as many arguments as possible on the first line. Continuation lines align at the column of
`(` + 1.

**Examples:**

```python
        modules_iter = sysfs_io.read_paths_int(id_paths, what="module number",
                                               val_if_not_found=None)

        for cpu, (path, module), (_, siblings_str) in zip(cpus_to_read, modules_iter,
                                                          siblings_iter):
```

### Alignment of Log Messages

Log messages follow the same alignment rules as function calls. If everything fits on one line,
keep it on one line. When splitting, prefer moving all arguments to continuation lines. However,
keeping some arguments on the first line is acceptable if it saves a line.

**Examples:**

```python
    # Good: Fits on one line.
    _LOG.debug("Cached: Read: CPU%d: MSR 0x%x%s", cpu, regaddr, self._pman.hostmsg)

    # Good: All arguments on the next line.
    _LOG.debug("Remote: Read: MSR 0x%x from CPUs %s%s, the command is: %s",
               regaddr, cpus_range, self._pman.hostmsg, cmd)

    # Good: Some arguments on the first line to save a line.
    _LOG.debug("Transaction %d: %s: %s: CPU%d: MSR 0x%x: 0x%x to '%s'%s, command: %s", index,
               transaction_type, operation_type, cpu, addr, regval, path, self._pman.hostmsg, cmd)
```

### Alignment of Assert Statements

When an assert statement does not fit on one line, the continuation line aligns right after
'assert ' (indent + 7).

**Examples:**

```python
    # Good: Proper alignment (4 spaces indent + 7 = column 11).
    assert list(noncomp_dies) == sorted(noncomp_dies), \
           "The package numbers returned are not in ascending order"

    # Good: Multi-line message with proper alignment.
    assert result == expected, \
           f"Bad result of bytesize({size}, decp={decp}):\n" \
           f"expected '{expected}', got '{result}'"

    # Bad: Incorrect alignment (off by one or more spaces).
    assert names == ["subdir", "test.fifo", "test.socket"], \
        f"sort_by='alphabetic' failed: {names}"

    # Bad: Message on the same line when it would exceed 100 characters.
    assert condition_is_true, "This is a very very long error message that goes way beyond the limit"
```

### Multi-line Strings

Keep the first line as close to the 100-character limit as possible. Each continued line should be
its own f-string, aligned with the opening quote.

Use `\` continuation only outside parentheses (where omitting it would be a syntax error). Inside
parentheses, `\` is not needed. Python handles implicit string concatenation automatically.

**Examples:**

```python
    # Good: Outside parens (return without parens), \ is required.
    return f"\nThe '{fpath}' file{self._pman.hostmsg} indicates that the '{opt}' kernel " \
           f"boot parameter is set, this may be the reason"

    # Good: Inside parens (function argument), \ is not needed.
    raise Error(f"The '{fpath}' file{self._pman.hostmsg} indicates that the '{opt}' kernel "
                f"boot parameter is set, this may be the reason")

    # Bad: First line too short (unnecessarily splits early).
    return f"\nThe '{fpath}' file{self._pman.hostmsg} indicates that " \
           f"the '{opt}' kernel boot parameter is set, this may be the reason"

    # Bad: Exceeds 100 characters on one line.
    return f"\nThe '{fpath}' file{self._pman.hostmsg} indicates that the '{opt}' kernel boot parameter is set, this may be the reason"

    # Bad: Using \ inside parentheses (redundant).
    raise Error(f"The '{fpath}' file{self._pman.hostmsg} indicates that the '{opt}' kernel " \
                f"boot parameter is set, this may be the reason")
```

## Whitespace & Formatting

### Quotes

Prefer double quotes. Use single quotes only when the string contains double quotes.

### Spaces Around Operators

Always use spaces around arithmetic operators (`+`, `-`, `*`, `/`, `//`, `%`, `**`) and comparison
operators (`==`, `!=`, `<`, `>`, `<=`, `>=`). This applies even when operators are used inside array
indices or other expressions.

For the assignment operator (`=`), use spaces around it in regular assignments, but do NOT use
spaces when passing keyword arguments to functions.

**Examples:**

```python
# Good: Spaces around operators in all contexts.
result = value + 1
matrix[fdx - 2][sdx - 2] + cost

# Good: Spaces around = in assignments, no spaces in keyword arguments.
result = 5
func(cpus=(1, 5))
obj.method(name="value", count=10)

# Bad: No spaces around operators.
result = value+1
matrix[fdx-2][sdx-2]+cost

# Bad: Spaces in keyword arguments.
obj.method(name = "value")
```

### Blank Lines Between Methods

Use one blank line between method definitions within a class. Do not use multiple blank lines.

**Example:**

```python
    def method_one(self):
        """First method."""
        pass

    def method_two(self):
        """Second method."""
        pass
```

### Blank Line After Docstring

Always include a blank line between a function/method docstring and its body, unless both the
docstring and body are one-liners, in which case the blank line is optional.

### Trailing Spaces and Newlines

Do not include trailing spaces at the end of lines. Ensure that files end with a single newline character.

### Dictionary Format

When defining a dictionary with multiple key-value pairs, use one key-value pair per line unless
the dictionary is very small and fits on one line.

Vertical alignment of values is optional. If you choose to align values, add spaces after the colon
`:`, not before it. This keeps the colons in a clean vertical line while padding the values.

**Examples:**

```python
    # Good: Aligned values with spaces after colon.
    _PKGINFO: Final[dict[str, dict[str, str]]] = {
        "fedora":  _FEDORA_PKGINFO,
        "cent_os": _FEDORA_PKGINFO,
    }

    # Good: No alignment.
    _PKGINFO: Final[dict[str, dict[str, str]]] = {
        "fedora": _FEDORA_PKGINFO,
        "cent_os": _FEDORA_PKGINFO,
    }

    # Bad: Spaces before colon.
    _PKGINFO: Final[dict[str, dict[str, str]]] = {
        "fedora"  : _FEDORA_PKGINFO,
        "cent_os" : _FEDORA_PKGINFO,
    }
```

## Exception Handling

### Exception Handling Approach

The project uses only `Error` and its subclasses (defined in `Exceptions.py`) as the exception
type. Standard Python exceptions like `OSError` are intercepted at the lowest levels and converted
to `Error` or an appropriate subclass. A non-`Error` exception escaping a pepc method is a bug.

### Exception Re-raise Rules

When re-raising, two cases apply:

**Same semantic type**: use `type(err)(...)` to preserve the exact subclass. `except Error`
catches subclasses like `ErrorNotFound`; hardcoding `Error(...)` would lose that.

```python
# Wrong: loses the original subclass.
except Error as err:
    raise Error(f"Failed to do X:\n{err.indent(2)}") from err

# Correct: preserves the original subclass.
except Error as err:
    raise type(err)(f"Failed to do X:\n{err.indent(2)}") from err
```

**Deliberate type change**: use the target type directly and document it in `Raises:`.

```python
except ErrorNotFound as err:
    raise ErrorNotSupported(f"Feature not available:\n{err.indent(2)}") from err
```

### Bug Sentinel Errors

When an error condition should never occur during correct program execution and its presence
indicates a programming bug, prefix the exception message with `BUG:`.

```python
raise Error(f"BUG: Unexpected state '{state}'")
```

### Exception Handling Formatting

Do not add blank lines before `except:`, `finally:`, or `else:` clauses.

## Documentation

### Docstrings Style

Use Google style for docstrings.

**Structure:**

- **First paragraph**: Summary of the method's purpose, written in imperative voice. Can be a

  single line or multiple lines. Start with an imperative verb (e.g., "Return", "Check", "Yield",
  "Test").

- **Subsequent paragraphs** (rarely needed): Additional descriptive paragraphs should be rarely

  needed. Use structured sections (`Args:`, `Returns:`, `Yields:`, `Notes:`, `Examples:`) instead,
  as they provide better organization and readability. Only add additional paragraphs if the
  information cannot be properly expressed in structured sections.

  Prefer a short `Notes:` bullet list over a prose paragraph, or add an `Examples:` section.
  A few concrete examples are often clearer to readers than a lengthy description.

- **Notes section** (optional): Use `Notes:` (plural) for additional details formatted as a bullet

  list. Common uses:

  - Validation requirements (e.g., "Methods do not validate the 'cpus' argument")
  - Thread-safety information
  - Performance considerations
  - Other important caveats
- **Args/Returns/Yields/Raises sections**:
  - `Args:` is mandatory if the method has parameters (except `self`)
  - `Returns:` is mandatory if the method returns a value (other than `None`)
  - `Yields:` is mandatory if the method is a generator
  - `Raises:` is mandatory for public methods that raise exceptions (except the base `Error`

    class), optional for private methods

**Guidelines:**

- For one-line docstrings, keep the closing `"""` on the same line (e.g., `"""Return the value."""`)
- For multi-line docstrings, put both the opening and closing `"""` on their own separate lines
- Do not repeat information that is already clear from the function signature and summary
- Do not repeat the type in `Args:`, `Returns:`, or `Yields:` sections. The type is already
  expressed in the function signature annotations.
- Prefer putting additional details in the `Notes:` section as bullet points rather than in

  paragraph form

- Skip detailed description paragraphs if the summary and Args/Returns/Notes sections are

  sufficient

- Use single quotes (not backticks) to reference variable names, function names, and similar

  identifiers in docstrings. Example: "See 'close()' for details" or "Returns the 'cpu' value".

- For helper functions that implement or wrap another function, reference the main function's

  arguments instead of repeating them when appropriate. Example: "Arguments are the same as in
  'main_function()'." This avoids repetition when argument lists are long or obvious from context.

**Examples:**

```python
# Good: Concise single-line summary.
def get_cpu_count(self) -> int:
    """Return the number of CPUs on the system."""

# Good: Using imperative voice, concise summary.
def read_msr(self, regaddr: int, cpus: Iterable[int]) -> Generator[tuple[int, int], None, None]:
    """
    Read MSR register from specified CPUs and yield the values. Both local and remote execution
    are supported.

    Args:
        regaddr: The MSR register address to read.
        cpus: The CPU numbers to read from.

    Yields:
        Tuples of (CPU number, register value).
    """

# Bad: Redundant body text, using "this method" instead of imperative voice.
def get_cpu_count(self) -> int:
    """
    Return the number of CPUs on the system.

    This method returns the number of CPUs that are available on the system.

    Returns:
        The number of CPUs.
    """
```

### Documenting Exceptions in Docstrings

Do not document `Error` itself, it is the common base class. Document subclasses that a public
method can raise. For private methods, document exceptions when helpful.

Use declarative statements, not conditional "if" clauses:

**Example:**

```python
    # Good.
    Raises:
        ErrorNotSupported: The file does not exist.

    # Bad.
    Raises:
        ErrorNotSupported: If the file does not exist.
```

### Docstring Continuation Line Alignment

Continuation lines in structured docstring elements (`Args:`, `Raises:`, etc.) align with the text
after the colon (`continuation column = colon column + 2`).

**Examples:**

```python
# Good: Continuation lines align with text after colon.
def write(self, regaddr: int, regval: int, cpus: Sequence[int]):
    """
    Write a value to an MSR on specified CPUs.

    Args:
        regaddr: The address of the MSR to write to.
        regval: The value to write to the MSR.
        cpus: CPU numbers to write the MSR on (the caller must validate CPU
              numbers).

    Raises:
        ErrorVerifyFailedPerCPU: If verification is enabled and the read-back value does
                                 not match the written value. The 'cpu' attribute of the
                                 exception will contain the CPU number where the
                                 verification failed.
    """

# Bad: Continuation lines do not align properly.
def write(self, regaddr: int, regval: int, cpus: Sequence[int]):
    """
    Write a value to an MSR on specified CPUs.

    Args:
        regaddr: The address of the MSR to write to.
        regval: The value to write to the MSR.
        cpus: CPU numbers to write the MSR on (the caller must validate CPU
            numbers).  # Wrong: not aligned with "CPU"

    Raises:
        ErrorVerifyFailedPerCPU: If verification is enabled and the read-back value does
                           not match the written value.  # Wrong: not aligned with "If"
    """
```

### Imperative Voice

Use imperative voice in docstrings and comments. Start with verbs like "Provide", "Return",
"Check", "Initialize".

**Examples:**

```python
    # Good: Imperative voice.
    """Provide helper methods for checking if tools are available on the system."""
    """Return the OS information dictionary."""
    """Check if the tool is installed on the target system."""

    # Bad: Declarative voice.
    """This module provides helper methods for checking if tools are available."""
    """This method returns the OS information dictionary."""
```

### Comment Punctuation

All comments should end with a period (`.`). Do not use semicolons (`;`) as punctuation in
comments or messages. Use a comma (`,`) or a period (`.`) instead.

Comments should explain **why**, not **what**. The code itself shows what happens. Only describe
the how when it is non-obvious.

Prefer placing comments on a separate line **before** the code they describe, rather than appending
them to the end of a code line. Short TODO/note annotations on `from __future__` imports or similar
one-off markers are fine inline.

```python
# WRONG: restates what the code already says.
# Flush the file to disk.
fobj.flush()

# RIGHT: explains why.
# Paranoid flush to minimise the chance of data loss on crash.
fobj.flush()

# OK: TODO-style annotation on a special import line.
from __future__ import annotations # Remove when switching to Python 3.10+.
```

When referring to a function, method, or other identifier in a comment, use single quotes with
parentheses for callables: `'configure()'`, `'close()'`. For non-callables, use single quotes
without parentheses: `'outdir'`, `'_pman'`.

### Messages

#### Small vs Capital Letters in Messages

Every log and exception message should start with a capital letter. After each colon in a message,
the next word should also be capitalized. One-line messages should not have a trailing period;
multi-line messages should use periods.

**Examples:**

```python
    # Good: Capital letters after each colon.
    _LOG.debug("Local: Read: CPU%d: MSR 0x%x: 0x%x", cpu, regaddr, val)
    _LOG.debug("Transaction: Remote: Write: Executing command%s: %s", hostmsg, cmd)
    raise Error(f"BUG: Invalid CPU number: {cpu}. Valid range is 0-{max_cpu}.")

    # Bad: Lowercase after colons.
    _LOG.debug("Local: read: CPU%d: msr 0x%x: 0x%x", cpu, regaddr, val)
```

## Markdown Documentation

### Backtick Usage

Use backticks for:

- **Tool and command names**: `pepc`, `git`, `pip3`, `uv`.
- **Subcommand names**: `pepc pstates`, `pepc cstates`.
- **Option names**: `--cpus`, `--max-freq`, `-H`.
- **File and directory paths**: `~/.bashrc`, `tests/emul-data/`, `/sys/devices/...`.
- **Environment variable names**: `PATH`, `MANPATH`.
- **Code identifiers**: function names, class names, and similar symbols, e.g., `read_msr()`,

  `ErrorNotFound`.

### Backtick Span Wrapping

Do not split a backtick-quoted span across lines. Keep the opening and closing backtick on the
same line. If adding the span would push the line past 100 characters, break the line before the
opening backtick.

### Link Wrapping

Do not split a `[text](url)` link across lines. After the link ends, continue text on the same
line and only break when the line would exceed 100 characters. If the link itself already reaches
or exceeds 100 characters, break the line immediately before or after the link.

**Correct:**

```markdown
Refer to the
[Performance Level to Frequency Mapping](#performance-level-to-frequency-mapping) section.

See [Pepc User Guide: Uncore](guide-uncore.md)
for details.
```

**Incorrect:**

```markdown
Refer to the [Performance Level to
Frequency Mapping](#performance-level-to-frequency-mapping) section.
```

## Code Organization

### Class Layout

The `__init__()` method should be defined at the top of the class, immediately after the class
docstring. The `close()` method and other special methods (e.g., `__enter__`, `__exit__`) should
go after `__init__()`. Regular methods should be defined after the special methods.

Avoid `__del__()`. See [Resource Cleanup](#resource-cleanup) for details.

The general order of methods in a class should be that the inner methods are defined before the
outer methods. For example, if a method A calls method B, then method B should be defined before
method A.

### Private vs Public Symbols

All private symbols must start with an underscore `_`. This applies to:

- Methods and functions
- Global variables, including constants
- Types, including `TypedDict` definitions

**Examples:**

```python
# Private constant
_DEFAULT_TIMEOUT = 30

# Private TypedDict
if typing.TYPE_CHECKING:
    class _DeviceInfoTypedDict(TypedDict):
        """
        ... Reasonable Docstring ...
        """
# Public constant
MAX_RETRIES = 5
```

### Import Statements

#### Prefer module imports over symbol imports

Prefer importing a module and referencing its symbols via the module name rather than importing
individual symbols with `from X import Y`. This makes the origin of each symbol obvious at the
call site and avoids ambiguity.

**Good:**

```python
from pepclibs.helperlibs import Logging

_LOG = Logging.getLogger(...)
```

**Bad:**

```python
from pepclibs.helperlibs.Logging import getLogger

_LOG = getLogger(...)
```

**Exceptions:**

- `from X import Error, ErrorNotSupported`: exception classes are always imported by name,
  because writing `Exceptions.Error` at every raise/catch site is noisy.
- `from typing import IO, Generator, Sequence`: typing symbols are always imported by name,
  never use `typing.IO`, `typing.Generator`, etc.
- Established ecosystem conventions, e.g. `import pandas as pd` / `pd.DataFrame`, are fine.
- Do not rename modules on import (e.g. `from X import _Mod as mod`) unless there is a specific
  reason. Use the real module name at the call site.

#### Multiple symbols per statement

When importing multiple symbols from the same module, use multiple separate `import` statements
rather than parentheses for multi-line imports. This makes imports easier to grep.

Pack as many names as fit within the 100-character line limit per statement. When they don't all
fit, start a new `from X import` statement for the remainder, again packing as many as fit.

**Good:**

```python
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorPerCPU
```

**Bad:**

```python
from pepclibs.helperlibs.Exceptions import (Error, ErrorNotSupported, ErrorPermissionDenied,
                                            ErrorPerCPU)
```

**Also bad (one name per line):**

```python
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.helperlibs.Exceptions import ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorPermissionDenied
from pepclibs.helperlibs.Exceptions import ErrorPerCPU
```

## Type Annotations & Type System

### Collection Types in Annotations

For function/method parameters, prefer the least restrictive type that is sufficient:

- Use `Iterable[T]` when the parameter is only iterated once.
- Use `Sequence[T]` when random access or multiple iterations are needed.
- Use `list[T]` or `tuple[T, ...]` only when mutation or a concrete type is required.

Avoid annotating parameters as `list` when `Iterable` or `Sequence` would work, it unnecessarily
restricts callers.

### Return Type Annotations

If a method does not return anything (i.e., it returns `None`), do not include a return type
annotation at all.

### Guarding Typing Imports with TYPE_CHECKING

Import typing utilities (`cast`, `TypedDict`, `Generator`, `Sequence`, etc.) under the
`typing.TYPE_CHECKING` guard to avoid runtime overhead.

```python
import typing

if typing.TYPE_CHECKING:
    from typing import cast, Generator, TypedDict, Sequence
    from some.module import SomeType

# Usage of cast in code.
if typing.TYPE_CHECKING:
    value = cast(int, some_value)
else:
    value = some_value
```

### Using TypedDict

Prefer `TypedDict` over plain `dict` when the structure is well-defined. Name with a `TypedDict`
suffix. Include a docstring with summary and `Attributes:` section.

Use `total=False` when building dictionaries key by key.

**Examples:**

```python
# Good: Using TypedDict with total=False.
import typing

if typing.TYPE_CHECKING:
    from typing import TypedDict

    class PCIInfoTypedDict(TypedDict, total=False):
        """PCI device information.

        Attributes:
            addr: PCI device address.
            vendorid: Vendor ID of the PCI device.
            devid: Device ID of the PCI device.
        """

        addr: str
        vendorid: int
        devid: int
```

## API Design & Conventions

### Prefer Immutable Collections

Prefer `tuple` over `list` and `frozenset` over `set` for collections that should not be modified
after creation.

When passing a small collection of items (e.g., CPU numbers), prefer a tuple over a list:

```python
    def read(self,
             regaddr: int,
             cpus: Iterable[int] | Literal["all"] = "all",
             verify: bool = False) -> Generator[tuple[int, int], None, None]:
```

When calling this method only for CPU 0, use a tuple for the `cpus` argument:

```python
    for cpu, val in self.read(regaddr=0x4E70, cpus=(0,), verify=True):
        ...
```

### Avoid None as Default Value

Avoid `None` as a default value when a same-type sentinel works:

- Strings: `""`
- Integers: `-1`
- Sequences: `()`

**Example:**

```python
    def process_data(self, name: str = "", count: int = -1, cpus: Sequence[int] = ()):
        if not name:
            name = "default"
        if count == -1:
            count = 10
        if not cpus:
            cpus = self.get_all_cpus()
```

### Converting from str to int/float

Prefer `Trivial.str_to_int()`, `Trivial.str_to_float()`, or `Trivial.str_to_num()` over built-in
`int()`/`float()`. Use built-ins only when the string is already verified to be valid.

### Using Keyword Arguments

Use keyword arguments when calling methods, in the same order as the signature:

```python
    def read(self,
             regaddr: int,
             cpus: Iterable[int] | Literal["all"] = "all",
             verify: bool = False) -> Generator[tuple[int, int], None, None]:
```

Call with keyword arguments:

```python
    for cpu, val in self.read(regaddr=0x4E70, cpus=cpus, verify=True):
        ...
```

### Exiting the Process

Use `raise SystemExit(code)` instead of `sys.exit()`. Always pass the exit code explicitly:

```python
# Wrong.
sys.exit(0)

# Right.
raise SystemExit(0)
```

### Paths: pathlib vs os

Prefer `pathlib.Path` for path manipulation over the `os` and `os.path` modules. Use `Path`
methods directly where possible:

```python
# Prefer.
path = Path("/some/dir") / "file.txt"
if path.is_dir():
    path.mkdir(parents=True)

# Avoid.
path = os.path.join("/some/dir", "file.txt")
if os.path.isdir(path):
    os.makedirs(path)
```

This is not a hard rule. When `pathlib.Path` is not the clearest choice, for example when a
library requires plain strings, or when manipulating a path with regex is simpler, prefer
whichever approach is cleaner.

### Resource Cleanup

Use `close()` for resource cleanup, not `__del__()`. `__del__()` is timing non-deterministic,
silently swallows exceptions, and may run during interpreter shutdown in an undefined state. Only
use it when there is a specific, well-justified reason. Document the justification in a comment.

```python
# Wrong.
class Reader:
    def __init__(self):
        self._fobj: IO[str] | None = open("data.txt")

    def __del__(self):
        if getattr(self, "_fobj", None):
            self._fobj.close()
            self._fobj = None

# Right.
class Reader:
    def __init__(self):
        self._fobj: IO[str] | None = open("data.txt")

    def close(self):
        if self._fobj is not None:
            self._fobj.close()
            self._fobj = None
```

### Context Managers

Inherit from `ClassHelpers.SimpleCloseContext` (from `pepclibs`) instead of defining
`__enter__()` and `__exit__()` manually. It implements them by calling `close()`, so defining
`close()` is all that is needed.

```python
# Wrong.
class Reader:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

# Right.
class Reader(ClassHelpers.SimpleCloseContext):
    pass  # __enter__ and __exit__ are provided by SimpleCloseContext.
```

### Avoid next() on Generators

Avoid calling `next()` directly on generators. It raises `StopIteration` if the generator is
exhausted, and unhandled `StopIteration` propagates silently in unexpected ways.

For extracting a single value from a generator, use a `for` loop with `return` and a trailing
`raise`:

```python
# Wrong: raises StopIteration if the generator yields nothing.
_, val, mname = next(self._get_epp_or_epb((cpu,), mnames))
return val, mname

# Right: explicit failure path.
for _, val, mname in self._get_epp_or_epb((cpu,), mnames):
    return val, mname
raise Error(f"BUG: No EPP/EPB value yielded for CPU {cpu}")
```

When an empty iterator should simply return a default or bail out (no error), use
`for/break/else` — the `else` block executes only when no `break` was hit (i.e., the iterator
was empty):

```python
for _, driver in self._get_driver(cpus, mnames):
    break
else:
    return ""  # Iterator was empty.
if driver != "intel_pstate":
    return ""
```

If `next()` is unavoidable, either pass a default value as the second argument
(`next(it, None)`) and check the result, or catch `StopIteration` explicitly.

### Using ClassHelpers.close()

Use `ClassHelpers.close()` in `close()` methods to release owned and borrowed attributes.

- **`close_attrs`**: attributes the class *owns*. Their `close()` is called, then the attribute is
  set to `None`.
- **`unref_attrs`**: attributes the class *borrows* (created externally). Only set to `None`,
  no `close()` called.

**Benefits over open-coded cleanup:**

- Tolerates attributes that were never set (`__init__` raised partway through): uses
  `getattr(..., None)` internally.
- The `_close_{attr}` flag lets you suppress `close()` for a specific attribute without changing
  the call site, which is useful when ownership is conditional.
- Logs a warning if an attribute name is not found on the object, catching typos at cleanup time.

**Drawback:** attribute names are plain strings, so IDEs and static analysis tools cannot follow
them.

For simple classes, open-coded cleanup is often just as clear. Use `ClassHelpers.close()` anyway.
The project follows this pattern consistently, and consistency has its own value.

```python
import typing
from pepclibs.helperlibs import LocalProcessManager

if typing.TYPE_CHECKING:
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

class Reader(ClassHelpers.SimpleCloseContext):
    def __init__(self, pman: ProcessManagerType | None = None):
        # When 'pman' is 'None', create a local process manager and own it (close on exit).
        # When provided by the caller, borrow it (do not close on exit).
        self._close_pman = pman is None
        if pman:
            self._pman = pman
        else:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        # '_close_pman' controls whether 'ClassHelpers.close()' calls 'self._pman.close()'.
        ClassHelpers.close(self, close_attrs=("_pman",))
```
