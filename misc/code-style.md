# Python Code Style Guide

This document provides guidelines for project coding style and conventions.

## Table of Contents

- [Code Style](#code-style)
  - [Alignment of Method Signatures](#alignment-of-method-signatures)
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

If possible, try to use a single line. If it does not fit, break the signature into multiple
lines and align the parameters vertically. Use one parameter per line in this case.

**Alignment Rule**: Use the opening parenthesis `(` as the anchor point.

- The first parameter starts immediately after the `(`
- All subsequent parameters must align vertically at the same column position (column of `(` + 1)

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

The `(` is at column 28, so all parameters start at column 29.

If the return type annotation is long, move it to the next line using a backslash `\` continuation.
Align the return type at an 4-character boundary so it ends near the 100-character line limit.

**Example 2:**

```python
    def read_multiple_features(self,
                               fnames: Sequence[str],
                               cpus: Sequence[int]) -> \
                                    Generator[tuple[int, dict[str, FeatureValueType]], None, None]:
```

The `(` is at column 29, so all parameters start at column 30.

**Note:** Even if all parameters fit on a single line, if the return type annotation is long,
it's better to break the signature into multiple lines and align the parameters vertically.

**Example 3:**

```python
    def check_is_feature_enabled(self,
                                 fname: str,
                                 cpus: Iterable[int] | Literal["all"] = "all") -> \
                                                        Generator[tuple[int, bool], None, None]:
```

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
