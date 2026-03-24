# Code Style Guide

This document provides guidelines for project coding style and conventions.

## Table of Contents

- [Formatting & Whitespace](#formatting--whitespace)
  - [Alignment of Method Signatures](#alignment-of-method-signatures)
  - [Alignment of Function Calls](#alignment-of-function-calls)
  - [Alignment of Log Messages](#alignment-of-log-messages)
  - [Quotes](#quotes)
  - [Spaces Around Operators](#spaces-around-operators)
  - [Blank Lines Between Methods](#blank-lines-between-methods)
  - [Blank Line After Docstring](#blank-line-after-docstring)
  - [Exception Handling Formatting](#exception-handling-formatting)
  - [Trailing Spaces and Newlines](#trailing-spaces-and-newlines)
  - [Dictionary Format](#dictionary-format)
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
  - [Importing Types from typing](#importing-types-from-typing)
  - [Guarding Typing Utilities with TYPE_CHECKING](#guarding-typing-utilities-with-type_checking)
  - [Using TypedDict](#using-typeddict)
- [API Design & Conventions](#api-design--conventions)
  - [Prefer Tuple Over List](#prefer-tuple-over-list)
  - [Avoid None as Default Value](#avoid-none-as-default-value)
  - [Prefer Frozenset and Tuples for Immutable Sets/Sequences](#prefer-frozenset-and-tuples-for-immutable-setssequences)
  - [Converting from str to int/float](#converting-from-str-to-intfloat)
  - [Using Keyword Arguments](#using-keyword-arguments)

## Formatting & Whitespace

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

**Algorithm:**

1. Count indentation spaces. Typically it is 0 for top-level functions and 4 for methods inside a
   class.
2. Count method name character-by-character (underscore counts as 1 character)
3. Use formula:
   `Parameter Indent = Indent Spaces + 4 + Method Name Length + 1`,
    where 4 is the length of "def ", and 1 is for the opening parenthesis `(`.

**Example 1:**

```python
    def is_feature_supported(self,
                             fname: str,
                             cpus: Iterable[int] | Literal["all"] = "all") -> bool:
```

The `(` is at column 28, so all parameters start at column 29. Each parameter is on its own line.

If the return type annotation is long, move it to the next line using a backslash `\` continuation.
Align the return type at an 4-character boundary so it ends near the 100-character line limit.

**Example 2:**

```python
    def read_multiple_features(self,
                               fnames: Sequence[str],
                               cpus: Sequence[int]) -> \
                                    Generator[tuple[int, dict[str, FeatureValueType]], None, None]:
```

The `(` is at column 29, so all parameters start at column 30. One parameter per line.

Note: Even if all parameters fit on a single line, if the return type annotation is long,
it's better to break the signature into multiple lines and align the parameters vertically, with
one parameter per line.

**Example 3:**

```python
    def check_is_feature_enabled(self,
                                 fname: str,
                                 cpus: Iterable[int] | Literal["all"] = "all") -> \
                                                        Generator[tuple[int, bool], None, None]:
```

### Alignment of Function Calls

When a function or method call does not fit on a single line, split it across multiple lines
following the same alignment rules as method signatures.

Use the opening parenthesis `(` as the anchor point:

- Fit as many arguments as possible on the first line without exceeding 100 characters
- When continuing on the next line, align arguments at the column of `(` + 1
- All subsequent arguments must align vertically at the same column position

**Algorithm:**

1. Count indentation spaces
2. Count characters up to and including the opening parenthesis `(`
3. Argument indent = Indent spaces + Character count to opening parenthesis (inclusive)

**Example 1:**

```python
        modules_iter = sysfs_io.read_paths_int(id_paths, what="module number",
                                               val_if_not_found=None)
```

The `(` is at column 47, so continuation arguments start at column 48.

**Example 2:**

```python
        for cpu, (path, module), (_, siblings_str) in zip(cpus_to_read, modules_iter,
                                                          siblings_iter):
```

The `(` after `zip` is at column 58, so `siblings_iter` starts at column 59.

### Alignment of Log Messages

Log messages follow the same alignment rules as function calls.

If the entire log message (including all arguments) fits on one line within the
100-character limit, keep it on one line.

Only split the message across multiple lines if it exceeds 100 characters. When splitting, prefer to
move all arguments to continuation lines, properly aligned. However, if moving all arguments to the
next line would require an additional line (compared to keeping some on the first line), it's
acceptable to keep some arguments on the same line as the format string.

**Example 1:**

```python
    # Good: Fits on one line.
    _LOG.debug("Cached: Read: CPU%d: MSR 0x%x%s", cpu, regaddr, self._pman.hostmsg)

    # Bad: Unnecessarily split when it fits on one line.
    _LOG.debug("Cached: Read: CPU%d: MSR 0x%x%s",
               cpu, regaddr, self._pman.hostmsg)
```

**Example 2:**

```python
    # Good: All arguments on the next line when the message is too long.
    _LOG.debug("Remote: Read: MSR 0x%x from CPUs %s%s, the command is: %s",
               regaddr, cpus_range, self._pman.hostmsg, cmd)

    # Bad: Some arguments on the same line as format string.
    _LOG.debug("Remote: Read: MSR 0x%x from CPUs %s%s, the command is: %s", regaddr, cpus_range,
               self._pman.hostmsg, cmd)
```

**Example 3:**

```python
    # Good: Keeps the same number of lines by having some arguments on the first line.
    _LOG.debug("Transaction %d: %s: %s: CPU%d: MSR 0x%x: 0x%x to '%s'%s, command: %s", index,
               transaction_type, operation_type, cpu, addr, regval, path, self._pman.hostmsg, cmd)

    # Bad: Adds an extra line without improving readability.
    _LOG.debug("Transaction %d: %s: %s: CPU%d: MSR 0x%x: 0x%x to '%s'%s, command: %s",
               index, transaction_type, operation_type, cpu, addr, regval, path, self._pman.hostmsg,
               cmd)
```

### Alignment of Assert Statements

When an assert statement with a message does not fit on a single line, split it across multiple
lines following the same alignment principle used for function calls.

Use the space after the 'assert' keyword as the anchor point. The continuation line with the
assertion message should align with the first character of the condition (right after 'assert ').

**Algorithm:**

1. Count indentation spaces
2. Add 7 for 'assert ' (6 characters + 1 space)
3. Continuation line indent = Indent spaces + 7

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

When splitting long strings (f-strings, return statements, string concatenations) across multiple
lines, aim to keep the first line as close to the 100-character limit as possible. This maximizes
readability while staying within the line length constraint.

Use backslash `\` continuation for multi-line strings. When using f-strings, each line should be its
own f-string. Align continuation lines with the opening quote of the first string.

**Examples:**

```python
    # Good: First line close to 100 chars, natural break point.
    return f"\nThe '{fpath}' file{self._pman.hostmsg} indicates that the '{opt}' kernel " \
           f"boot parameter is set, this may be the reason"
    # Bad: First line too short (unnecessarily splits early).
    return f"\nThe '{fpath}' file{self._pman.hostmsg} indicates that " \
           f"the '{opt}' kernel boot parameter is set, this may be the reason"
    # Bad: Exceeds 100 characters on one line.
    return f"\nThe '{fpath}' file{self._pman.hostmsg} indicates that the '{opt}' kernel boot parameter is set, this may be the reason"
```

### Quotes

Prefer using double quotes whenever possible. Use single quotes only when the string contains double
quotes that would require escaping. Or when you have to.

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

### Exception Handling Formatting

Do not add blank lines before `except:`, `finally:`, or `else:` clauses in try/except blocks.

```python
# Good
try:
    do_something()
except Error:
    handle_error()
finally:
    cleanup()

# Bad
try:
    do_something()

except Error:
    handle_error()

finally:
    cleanup()
```

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

No need to document the 'Error' exception in docstrings, as it is a common base class for all
exceptions in the project. However, document all other exceptions that a public method can raise. In
case of private methods, it is not necessary to document exceptions in docstrings, but it is
recommended to document them if it does not make docstrings too repetitive or if the case is tricky.

**Exception Description Style**: Use declarative statements instead of conditional "if" clauses when
describing when exceptions are raised.

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

When documenting arguments, exceptions, attributes, return values, or other structured docstring
elements, continuation lines must align with the text that follows the colon on the first line.

**Alignment Rule**: Find the position of the colon `:`, add 1 to account for the space after the
colon, and align all continuation lines at that column position.

**Formula**: `Continuation column = colon column + 2` (colon itself + space after colon)

This alignment ensures visual consistency and makes it easier to scan docstrings for information.

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

Use imperative voice in docstrings and comments. This style is concise and consistent with Linux
kernel documentation practices. Start docstrings with imperative verbs like "Provide", "Return",
"Check", or "Initialize" rather than declarative forms like "This module provides" or "This method
returns".

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

All comments in the code should end with a period (`.`), even if they are single-line comments
containing only one sentence. This includes inline comments, standalone comments, and multi-line
comment blocks.

### Messages

#### Small vs Capital Letters in Messages

Every log message and exception message should start with a capital letter. One-line messages do
not need to end with a period, but multi-line messages or messages with multiple sentences should
use periods.

When a message contains a colon, the text immediately following the colon should also start with a
capital letter. This applies to all colons in the message, creating a consistent hierarchical
structure.

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

When importing multiple symbols from the same module, prefer using multiple separate `import`
statements rather than using parentheses for multi-line imports. This makes it easier to grep for
specific imports and understand dependencies.

**Rationale**: Separate import statements allow for easy searching with tools like `grep` to find
where specific symbols are imported from. Each import line is self-contained and can be found with
a simple text search.

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

**Guidelines:**

- If all imports fit on one line within the 100-character limit, use a single import statement.
- If imports don't fit on one line, split them into multiple import statements from the same
  module.
- Group related imports together (e.g., base exceptions on one line, specialized exceptions on
  another).
- Maintain alphabetical ordering within each import statement when practical.

## Type Annotations & Type System

### Return Type Annotations

If a method does not return anything (i.e., it returns `None`), do not include a return type
annotation at all.

### Importing Types from typing

Import types from `typing` that are used only for type annotations under the `typing.TYPE_CHECKING`
guard. This prevents runtime overhead and circular import issues.

**Examples:**

```python
import typing

if typing.TYPE_CHECKING:
    from typing import Generator, TypedDict
    from some.module import SomeType
```

### Guarding Typing Utilities with TYPE_CHECKING

Typing utilities from the `typing` module that are only used for type checking should always be
imported under the `typing.TYPE_CHECKING` guard. This ensures zero runtime overhead, since these
utilities are only used by type checkers and not during actual program execution.

Guard all utilities, for example:

- `cast()`: Type casting function
- `TypedDict`: Base class for typed dictionaries
- `Generator`, `Sequence`, `Iterable`, etc.: Generic types for annotations

**Examples:**

```python
import typing

if typing.TYPE_CHECKING:
    from typing import cast, Generator, TypedDict, Sequence

# Usage of cast in code.
if typing.TYPE_CHECKING:
    value = cast(int, some_value)
else:
    value = some_value
```

### Using TypedDict

Prefer using `TypedDict` over plain `dict` when the dictionary structure is well-defined and
consistent. This provides better type safety and improves code documentation.

Naming Convention: `TypedDict` type names should have the `TypedDict` suffix to clearly indicate
they are TypedDict types.

**Documentation:**

TypedDict classes must have a docstring with:

- A short summary describing what the TypedDict represents
- An `Attributes:` section documenting each field

There should be a blank line between the docstring summary and the `Attributes:` section.

**Using `total=False`:**

When building dictionaries key by key, use `total=False` in the TypedDict definition. This is more
convenient than initializing all keys upfront or using type casting.

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

### Prefer Tuple Over List

One of the patterns is to pass a collection of items to a method. For example, passing one or two CPU
numbers to a method. In such cases, prefer using a tuple instead of a list. For example:

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

When defining optional parameters with default values, avoid using `None` as the default value if
it is possible to use a special value of the same type as the parameter.

**Guidelines:**

- For strings: use `""` (empty string) as the default value
- For integers: use an unused number, such as `-1`
- For sequences: use an empty tuple `()`

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

### Prefer Frozenset and Tuples for Immutable Sets/Sequences

When defining a collection of items that should not be modified after creation, prefer using
`frozenset` instead of `set` and `tuple` instead of `list`.

### Converting from str to int/float

When converting a string to an integer or float, prefer using `Trivial.str_to_int()`,
`Trivial.str_to_float()`, or `Trivial.str_to_num()` instead of the built-in `int()` or `float()`.
These methods provide better error handling and support for different number formats. Use the
built-in methods only if it is already verified that the string is a valid number and does not
require special handling.

### Using Keyword Arguments

If a method signature includes keyword arguments, use keyword arguments when calling the method, and
maintain the same order as in the signature. For example:

```python
    def read(self,
             regaddr: int,
             cpus: Iterable[int] | Literal["all"] = "all",
             verify: bool = False) -> Generator[tuple[int, int], None, None]:
```

When calling this method, use keyword arguments in the same order:

```python
    for cpu, val in self.read(regaddr=0x4E70, cpus=cpus, verify=True):
        ...
```
