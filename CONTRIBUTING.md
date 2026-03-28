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
  - [Exception Handling Formatting](#exception-handling-formatting)
- [Documentation](#documentation)
  - [Docstrings Style](#docstrings-style)
  - [Documenting Exceptions in Docstrings](#documenting-exceptions-in-docstrings)
  - [Docstring Continuation Line Alignment](#docstring-continuation-line-alignment)
  - [Imperative Voice](#imperative-voice)
  - [Comment Punctuation](#comment-punctuation)
  - [Messages](#messages)
    - [Small vs Capital Letters in Messages](#small-vs-capital-letters-in-messages)
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
parentheses, `\` is not needed — Python handles implicit string concatenation automatically.

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

**Same semantic type** — use `type(err)(...)` to preserve the exact subclass. `except Error`
catches subclasses like `ErrorNotFound`; hardcoding `Error(...)` would lose that.

```python
# Wrong: loses the original subclass.
except Error as err:
    raise Error(f"Failed to do X:\n{err.indent(2)}") from err

# Correct: preserves the original subclass.
except Error as err:
    raise type(err)(f"Failed to do X:\n{err.indent(2)}") from err
```

**Deliberate type change** — use the target type directly and document it in `Raises:`.

```python
except ErrorNotFound as err:
    raise ErrorNotSupported(f"Feature not available:\n{err.indent(2)}") from err
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
- For multi-line docstrings, put the closing `"""` on a separate line
- Do not repeat information that is already clear from the function signature and summary
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

Do not document `Error` itself — it is the common base class. Document subclasses that a public
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

All comments should end with a period (`.`).

### Messages

#### Small vs Capital Letters in Messages

Every log and exception message should start with a capital letter. After each colon in a message,
the next word should also be capitalized. One-line messages do not need a trailing period; multi-line
messages should use periods.

**Examples:**

```python
    # Good: Capital letters after each colon.
    _LOG.debug("Local: Read: CPU%d: MSR 0x%x: 0x%x", cpu, regaddr, val)
    _LOG.debug("Transaction: Remote: Write: Executing command%s: %s", hostmsg, cmd)
    raise Error(f"BUG: Invalid CPU number: {cpu}. Valid range is 0-{max_cpu}.")

    # Bad: Lowercase after colons.
    _LOG.debug("Local: read: CPU%d: msr 0x%x: 0x%x", cpu, regaddr, val)
```

## Code Organization

### Class Layout

The `__init__()` method should be defined at the top of the class, immediately after the class
docstring. The destructor and other special methods (e.g., `__enter__`, `__exit__`) should go after
`__init__()`. Regular methods should be defined after the special methods.

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
