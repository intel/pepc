# AI Style Rules

Compact reference for AI code generation. Human docs: [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Checklist

- [ ] Function signature splits: ONE parameter per line
- [ ] Comments end with `.`
- [ ] Inline comments: prefer a separate line before the code; avoid appending to code lines
- [ ] Messages: capital after start and every `:`
- [ ] Dict: spaces AFTER `:`, never before
- [ ] No trailing spaces; files end with single newline
- [ ] Imports: prefer module imports (`from X import Mod` then `Mod.symbol`); exceptions: error
  classes, `typing` symbols, and established ecosystem patterns (e.g., pandas)
- [ ] Imports: do not rename modules on import (`import X as Y`); use the real name
- [ ] Imports: multiple statements, no parentheses; pack as many names per line as fit in 100 chars
- [ ] Multi-line strings: first line near 100 chars
- [ ] TypedDict: `total=False` when building key-by-key
- [ ] Module constants: `frozenset()`/`tuple()`, not `set()`/`list()`; prefer immutable
  collections generally
- [ ] pepclibs file I/O: `_sysfs_io` methods only
- [ ] Blank line after multi-line docstring before body
- [ ] One blank line between class methods
- [ ] Re-raise: `type(err)(...)` to preserve subclass
- [ ] "Should never happen" errors: prefix message with `BUG:`
- [ ] `Raises:` docstring: declarative, not "if" clauses
- [ ] Keyword args when calling methods; same order as signature
- [ ] `\` continuation only outside parentheses; never inside
- [ ] No blank lines before `except:`/`finally:`/`else:`
- [ ] `Trivial.str_to_int()`/`str_to_num()` instead of `int()`/`float()`
- [ ] Default values: `""` not `None`, `()` not `None`, `-1` not `None`
- [ ] `raise SystemExit(code)` not `sys.exit()`; always pass the exit code
- [ ] Resource cleanup: use `close()`, not `__del__()`; `__del__` timing is non-deterministic,
  it silently swallows exceptions, and may run during interpreter shutdown in an undefined state.
  Only use it when there is a specific, well-justified reason
- [ ] Context managers: inherit from `ClassHelpers.SimpleCloseContext` instead of defining
  `__enter__`/`__exit__` manually
- [ ] Paths: prefer `pathlib.Path` and its methods over `os`/`os.path`; skip when `str` is
  cleaner due to many `Path`↔`str` conversions
- [ ] Avoid `next()` on generators. Use a `for` loop with `return` and a trailing `raise` for
  single-value extraction; use `for/break/else` when an empty iterator should produce a default.
  If `next()` is unavoidable, either pass a default value or handle `StopIteration` explicitly.

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

- Outside parens → `\` required (syntax error otherwise).
- Inside parens → no `\`; Python handles implicit concatenation.

```python
# Outside parens (\  required)
return f"Long message text that goes up to natural break point near column 100 " \
       f"continuation here"

# Inside parens (no \)
raise Error(f"Long message text that goes up to natural break point near column 100 "
            f"continuation here")

# Bad: \ inside parens (redundant)
raise Error(f"Long message text near column 100 " \
            f"continuation here")
```

---

## Exception Re-raise

Two cases:

**Same semantic type**: use `type(err)(...)` to preserve the exact subclass.

```python
# Wrong: loses the original subclass.
except Error as err:
    raise Error(f"Failed to do X:\n{err.indent(2)}") from err

# Correct: preserves the subclass.
except Error as err:
    raise type(err)(f"Failed to do X:\n{err.indent(2)}") from err
```

**Deliberate type change**: use the target type directly, document in `Raises:`.

```python
except ErrorNotFound as err:
    raise ErrorNotSupported(f"Feature not available:\n{err.indent(2)}") from err
```

**Bug sentinel**: prefix the message with `BUG:` when the error should never happen and
indicates a programming error.

```python
raise Error(f"BUG: Unexpected state '{state}'")
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

All end with `.` No semicolons (`;`): use `,` or `.` instead.

Comments should explain **why**, not **what**. The code itself shows what happens. Only describe
the how when it is non-obvious.

Prefer placing comments on a separate line **before** the code they describe rather than appending
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

Refer to callables as `'configure()'`, `'close()'`; non-callables as `'outdir'`, `'_pman'`.

Violation regex: `^\s*#[^#].*[^.]$`

---

## Messages

Capital letter at start and after every `:`. One-line: no period. Multi-line: use periods.

```python
_LOG.debug("Local: Read: CPU%d: MSR 0x%x", cpu, addr)    # RIGHT
_LOG.debug("local: read: CPU%d: msr 0x%x", cpu, addr)    # WRONG
```

---

## Docstrings

Google style. Imperative voice (`"""Return ..."""` not `"""This method returns ..."""`).

Structure: summary → blank line → Args → Returns/Yields → Raises → Notes (`-` bullet list) → Examples.

- One-liner: `"""` on same line.
- Multi-liner: opening and closing `"""` each on their own line; blank line before body.
- Reference identifiers with single quotes: `'close()'`, `'cpu'`.
- Helper wrappers: "Arguments are the same as in 'main_function()'.".
- Do not repeat the type in `Args:`, `Returns:`, or `Yields:`. It is already in the
  signature.
- Keep the long description (between summary and `Args:`) short or omit it entirely. Put details
  in `Notes:` as a bullet list. Add `Examples:` instead of prose when possible, a few concrete
  examples are often clearer than a lengthy description.

```python
# WRONG: type repeated
Args:
    outdir: Path: The output directory.
Returns:
    Path: The log file path.

# RIGHT: type omitted
Args:
    outdir: The output directory.
Returns:
    The log file path.
```

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

## Type Annotations

Import typing utilities under `TYPE_CHECKING`. Use `import typing` then `if typing.TYPE_CHECKING:`.
For `cast`, guard the call site too.

For parameter types, prefer the least restrictive collection type: `Iterable[T]` if iterated once,
`Sequence[T]` if indexed or iterated multiple times, `list[T]` only if mutation is required.

```python
import typing

if typing.TYPE_CHECKING:
    from typing import cast, Generator, Sequence
    from some.module import SomeType

# cast usage at call site:
if typing.TYPE_CHECKING:
    value = cast(int, some_value)
else:
    value = some_value
```

If a method returns `None`, omit the return type annotation entirely.

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
