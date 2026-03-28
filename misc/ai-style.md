# AI Style Rules

Compact reference for AI code generation. Human docs: [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Checklist

- [ ] Function signature splits: ONE parameter per line
- [ ] Comments end with `.`
- [ ] Messages: capital after start and every `:`
- [ ] Dict: spaces AFTER `:`, never before
- [ ] No trailing spaces; files end with single newline
- [ ] Imports: multiple statements, no parentheses; pack as many names per line as fit in 100 chars
- [ ] Multi-line strings: first line near 100 chars
- [ ] TypedDict: `total=False` when building key-by-key
- [ ] Module constants: `frozenset()`/`tuple()`, not `set()`/`list()`
- [ ] pepclibs file I/O: `_sysfs_io` methods only
- [ ] Blank line after multi-line docstring before body
- [ ] One blank line between class methods
- [ ] Re-raise: `type(err)(...)` to preserve subclass
- [ ] `Raises:` docstring: declarative, not "if" clauses
- [ ] Keyword args when calling methods; same order as signature
- [ ] `\` continuation only outside parentheses; never inside
- [ ] No blank lines before `except:`/`finally:`/`else:`
- [ ] `Trivial.str_to_int()`/`str_to_num()` instead of `int()`/`float()`
- [ ] Default values: `""` not `None`, `()` not `None`, `-1` not `None`
- [ ] Prefer tuples over lists for small collections

---

## Line Limit

100 chars hard limit.

---

## Function Signatures

If fits on one line → keep it. Otherwise: one parameter per line.

Alignment: `indent + len("def ") + len(func_name) + len("(")`.

Long return type → `\` continuation, align at 4-char boundary near col 100.

```python
# WRONG
def method(self, param1: int,
           param2: str): ...

# RIGHT
def method(self,
           param1: int,
           param2: str): ...

# RIGHT: long return type
def read_features(self,
                  fnames: Sequence[str],
                  cpus: Sequence[int]) -> \
                       Generator[tuple[int, dict[str, FeatureValueType]], None, None]:
```

---

## Function Calls

Fit as many args on first line as possible. Continuation aligns at opening `(` + 1.

```python
result = some_function(arg1, arg2, arg3,
                       arg4, arg5)
```

---

## Log Messages

Fits on one line → keep it. Otherwise prefer ALL args on continuation. Exception: keep some on
first line if it saves a line.

```python
_LOG.debug("Remote: Read: MSR 0x%x from CPUs %s%s, the command is: %s",
           regaddr, cpus_range, self._pman.hostmsg, cmd)
```

---

## Strings

Maximize first line length (~95-100 chars). Each continuation is its own f-string. Align with
opening quote.

- Outside parens → `\` required.
- Inside parens → no `\`.

```python
# Outside parens
msg = f"Long message text that goes up to natural break point near column 100 " \
      f"continuation here"

# Inside parens (no \)
raise Error(f"Long message text that goes up to natural break point near column 100 "
            f"continuation here")
```

---

## Asserts

Continuation aligns at `indent + 7`.

```python
    assert condition, \
           "Error message"
```

---

## Comments

All end with `.`

Violation regex: `^\s*#[^#].*[^.]$`

---

## Messages

Capital letter at start and after every `:`. One-line: period optional. Multi-line: use periods.

```python
_LOG.debug("Local: Read: CPU%d: MSR 0x%x", cpu, addr)    # RIGHT
_LOG.debug("local: read: CPU%d: msr 0x%x", cpu, addr)    # WRONG
```

---

## Docstrings

Google style. Imperative voice (`"""Return ..."""` not `"""This method returns ..."""`).

Structure: summary → blank line → Args → Returns/Yields → Raises → Notes (bullet list).

- One-liner: `"""` on same line.
- Multi-liner: closing `"""` on own line; blank line before body.
- Reference identifiers with single quotes: `'close()'`, `'cpu'`.
- Helper wrappers: "Arguments are the same as in 'main_function()'."

### Raises: Section

- Only `Error` subclasses (`ErrorNotSupported`, `ErrorNotFound`, etc.), never `Error` itself.
- Declarative voice, not "if" clauses.

```python
# RIGHT
Raises:
    ErrorNotSupported: The file does not exist.

# WRONG
Raises:
    ErrorNotSupported: If the file does not exist.
```

### Continuation Alignment

`continuation_column = colon_column + 2`

```python
    Args:
        cpus: CPU numbers to write the MSR on (the caller must validate CPU
              numbers).
```

---

## Blank Lines

- One blank line between class methods.
- No blank lines before `except:`/`finally:`/`else:`.
- Blank line between multi-line docstring and body.

---

## Operators

Spaces around `+`, `-`, `*`, `/`, `//`, `%`, `**`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `=`.
No spaces in keyword args: `func(name="value")`.

---

## Dictionaries

Spaces AFTER `:`, never before. Extra spaces after `:` for alignment OK.

```python
{"key": value}          # RIGHT
{"key":  value}         # RIGHT (aligned)
{"key" : value}         # WRONG
```

---

## Exceptions

Only `Error` and subclasses from `Exceptions.py`. Non-`Error` escaping a pepc method = bug.

### Re-raise

Same type → `type(err)(...)`. Deliberate type change → target type directly, document in `Raises:`.

```python
# Same type: preserves subclass.
except Error as err:
    raise type(err)(f"Failed:\n{err.indent(2)}") from err

# Deliberate change.
except ErrorNotFound as err:
    raise ErrorNotSupported(f"Not available:\n{err.indent(2)}") from err
```

### Formatting

No blank lines before `except:`/`finally:`/`else:`.

---

## Types

- Return type annotation: omit if `None`.
- `typing` imports under `TYPE_CHECKING` guard.
- `cast()`, `TypedDict`, `Generator`, etc. under `TYPE_CHECKING`.
- TypedDict names: `...TypedDict` suffix. Docstring with `Attributes:` section.
- `total=False` when building dict key-by-key.
- Private types start with `_`.

---

## Collections

Module-level constants: `frozenset()` not `set()`, `tuple()` not `list()`.

```python
_NAMES: Final[frozenset[str]] = frozenset({
    "a",
    "b",
})
```

---

## Imports

Multiple statements, no parentheses. If > 100 chars → split into multiple `from X import` lines.

```python
# RIGHT
from module import A, B, C
from module import D, E

# WRONG
from module import (A, B, C,
                    D, E)
```

---

## File I/O (pepclibs)

All via `self._sysfs_io`: `.read()`, `.write_verify()`, `.read_paths()`.
Never `open()` or `pman.read_file()`.

---

## API Conventions

- Prefer tuples over lists for small collections: `cpus=(0,)`.
- Defaults: `""` not `None`, `()` not `None`, `-1` not `None`.
- `Trivial.str_to_int()`/`str_to_float()`/`str_to_num()` instead of `int()`/`float()`.
- Keyword args when calling; same order as signature.
- Prefer double quotes. Single quotes only to avoid escaping.

---

## Class Layout

`__init__` → `__del__`/`__enter__`/`__exit__` → inner methods → outer methods (callees before
callers). Private symbols start with `_`.

---

## Violation Regexes

```
Comment without period:          ^\s*#[^#].*[^.]$
Lowercase after colon in msg:    ["'].*:\s+[a-z]
Space before dict colon:         {\s*["'][^"']+["']\s+:
Multi-param on same line:        def \w+\([^,]+,\s*[^,]+,
Parenthesized import:            from .* import \(
```

---

## Decision Tree

```
line > 100 chars?
├─ NO → one line
└─ YES
    ├─ signature → one param/line, aligned
    ├─ call → align at ( + 1
    ├─ log → all args on continuation (or keep some if saves a line)
    ├─ string → max first line ~100, continue with own f-string
    └─ assert → align at indent + 7
```
