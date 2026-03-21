# Python Code Style Guide

This document provides guidelines for project coding style and conventions.

## Alignment of Method Signatures

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
    def read_features_nonorm(self,
                             fnames: Sequence[str],
                             cpus: Sequence[int]) -> \
                                    Generator[tuple[int, dict[str, FeatureValueType]], None, None]:
```

The `(` is at column 29, so all parameters start at column 30.

**Note:** Even if all parameters fit on a single line, if the return type annotation is long,
it's better to break the signature into multiple lines and align the parameters vertically.

**Example 3:**

```python
    def is_feature_enabled_norm(self,
                                fname: str,
                                cpus: Iterable[int] | Literal["all"] = "all") -> \
                                                        Generator[tuple[int, bool], None, None]:
```

## Using Keyword Arguments

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
