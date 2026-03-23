# Python Code Style Guide

This document provides guidelines for project coding style and conventions.

## Table of Contents

- [Code Style](#code-style)
  - [Alignment of Method Signatures](#alignment-of-method-signatures)
  - [Alignment of Function Calls](#alignment-of-function-calls)
  - [Using Keyword Arguments](#using-keyword-arguments)
  - [Blank Lines Between Methods](#blank-lines-between-methods)
  - [Class Layout](#class-layout)
  - [Documenting Exceptions in Docstrings](#documenting-exceptions-in-docstrings)
- [Conventions](#conventions)
  - [Prefer Tuple Over List](#prefer-tuple-over-list)
  - [Avoid None as Default Value](#avoid-none-as-default-value)
  - [Prefer Frozenset and Tuples for Immutable Sets/Sequences](#prefer-frozenset-and-tuples-for-immutable-setssequences)

## Code Style

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
# Good: All parameters fit on one line
def short_func(param1: int, param2: str) -> bool:

# Good: Split with one parameter per line
def long_function_name(self,
                       param1: int,
                       param2: str,
                       param3: bool = False) -> dict:

# Bad: Multiple parameters on one line when split
def long_function_name(self, param1: int,
                       param2: str, param3: bool = False) -> dict:

# Bad: Incorrect alignment
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
    # Good: Fits on one line
    _LOG.debug("Cached: Read: CPU%d: MSR 0x%x%s", cpu, regaddr, self._pman.hostmsg)

    # Bad: Unnecessarily split when it fits on one line
    _LOG.debug("Cached: Read: CPU%d: MSR 0x%x%s",
               cpu, regaddr, self._pman.hostmsg)
```

**Example 2:**

```python
    # Good: All arguments on the next line when the message is too long
    _LOG.debug("Remote: Read: MSR 0x%x from CPUs %s%s, the command is: %s",
               regaddr, cpus_range, self._pman.hostmsg, cmd)

    # Bad: Some arguments on the same line as format string
    _LOG.debug("Remote: Read: MSR 0x%x from CPUs %s%s, the command is: %s", regaddr, cpus_range,
               self._pman.hostmsg, cmd)
```

**Example 3:**

```python
    # Good: Keeps the same number of lines by having some arguments on the first line
    _LOG.debug("Transaction %d: %s: %s: CPU%d: MSR 0x%x: 0x%x to '%s'%s, command: %s", index,
               transaction_type, operation_type, cpu, addr, regval, path, self._pman.hostmsg, cmd)

    # Bad: Adds an extra line without improving readability
    _LOG.debug("Transaction %d: %s: %s: CPU%d: MSR 0x%x: 0x%x to '%s'%s, command: %s",
               index, transaction_type, operation_type, cpu, addr, regval, path, self._pman.hostmsg,
               cmd)
```

### Quotes

Prefer using double quotes whenever possible. Use single quotes only when the string contains double
quotes that would require escaping. Or when you have to.

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

### Class Layout

The `__init__()` method should be defined at the top of the class, immediately after the class
docstring. The destructor and other special methods (e.g., `__enter__`, `__exit__`) should go after
`__init__()`. Regular methods should be defined after the special methods.

The general order of methods in a class should be that the inner methods are defined before the
outer methods. For example, if a method A calls method B, then method B should be defined before
method A.

### Documenting Exceptions in Docstrings

No need to document the 'Error' exception in docstrings, as it is a common base class for all
exceptions in the project. However, document all other exceptions that a public method can raise. In
case of private methods, it is not necessary to document exceptions in docstrings, but it is
recommended to document them if it does not make docstrings too repetitive or if the case is tricky.

### Small vs Capital Letters in Messages

Every log message and exception message should start with a capital letter. One-line messages do
not need to end with a period, but multi-line messages or messages with multiple sentences should
use periods.

When a message contains a colon, the text immediately following the colon should also start with a
capital letter. This applies to all colons in the message, creating a consistent hierarchical
structure.

**Examples:**

```python
    # Good: Capital letters after each colon
    _LOG.debug("Local: Read: CPU%d: MSR 0x%x: 0x%x", cpu, regaddr, val)
    _LOG.debug("Transaction: Remote: Write: Executing command%s: %s", hostmsg, cmd)
    raise Error(f"BUG: Invalid CPU number: {cpu}. Valid range is 0-{max_cpu}.")

    # Bad: Lowercase after colons
    _LOG.debug("Local: read: CPU%d: msr 0x%x: 0x%x", cpu, regaddr, val)
```

## Conventions

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
