# AI Coding Style Guide

This document provides structured coding style rules optimized for AI processing and validation. For human-readable documentation, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Quick Validation Checklist

Before completing any code changes, verify:
- [ ] **CRITICAL: All function signatures with splits have ONE parameter per line (no `self, param:` on same line)**
- [ ] All function signature splits follow alignment rules (one parameter per line)
- [ ] All comments end with a period (`.`)
- [ ] All log/exception messages start with capital letters
- [ ] All dictionary spaces are after `:`, not before
- [ ] No trailing spaces on any line
- [ ] All imports split across multiple statements (no parentheses)
- [ ] All multi-line strings have first line close to 100 chars
- [ ] All TypedDict definitions use `total=False` when building dicts key-by-key
- [ ] All module-level constant collections use `frozenset()` or `tuple()`, not `set()` or `list()`
- [ ] All file I/O operations in pepclibs use `_sysfs_io` methods, not direct reads

## MOST COMMON MISTAKE: Function Signature Splitting

**THE RULE:** When a function signature is split across multiple lines, put EACH parameter on its OWN line.

**WRONG (most common mistake):**
```python
def method(self, param1: Type1,
           param2: Type2): ...

def __init__(self, pman: Type = None,
             cpuinfo: Type = None): ...
```

**CORRECT:**
```python
def method(self,
           param1: Type1,
           param2: Type2): ...

def __init__(self,
             pman: Type = None,
             cpuinfo: Type = None): ...
```

**Remember:** Even if there are only 2 parameters total (self + one other), if the signature must be split, put them on separate lines.

## Line Length Rules

**Hard limit**: 100 characters per line

**Decision Tree for Line Splitting:**

1. **Does entire statement fit on one line within 100 chars?**
   - YES → Keep on one line
   - NO → Go to step 2

2. **What type of statement?**
   - Function signature → Go to "Function Signature Rules"
   - Function call → Go to "Function Call Rules"
   - Log message → Go to "Log Message Rules"
   - String literal/f-string → Go to "String Splitting Rules"
   - Assert statement → Go to "Assert Rules"

### Function Signature Rules

**Pattern Recognition:**
```regex
^(\s*)def (\w+)\((.*)\) -> (.*):\s*$
```

**Algorithm:**
1. If entire signature (including return type) fits in 100 chars → keep on one line
2. Otherwise:
   - Split with ONE parameter per line
   - Align parameters at column: `indent + 4 + len(func_name) + 1`
   - If return type is long, move to continuation line with `\`

**Template:**
```python
def method_name(self,
                parameter1: Type1,
                parameter2: Type2,
                parameter3: Type3 = default) -> ReturnType:
```

**Critical Rules:**
- NEVER put multiple parameters on same line after split
- ALWAYS align all parameters at exact same column
- Calculate alignment: `indent_spaces + 4 + method_name_length + 1`

**Anti-patterns to Reject:**
```python
# WRONG: Multiple parameters on same line after split
def func(self, param1: int,
         param2: str): ...

# WRONG: Even if only 2 parameters, still split them
def method(self, cpus: Sequence[int]) -> ReturnType:  # This violates if split needed

# WRONG: When split, self and first param on same line
def __init__(self, pman: Type = None,
             cpuinfo: Type = None): ...

# CORRECT: Each parameter on its own line
def __init__(self,
             pman: Type = None,
             cpuinfo: Type = None): ...

# CORRECT: One parameter per line
def method(self,
           cpus: Sequence[int]) -> ReturnType:

# WRONG: Incorrect alignment
def func(self,
      param1: int,
      param2: str): ...
```

### Function Call Rules

**Algorithm:**
1. Fit as many arguments as possible on first line within 100 chars
2. Continuation lines align at: `indent + chars_to_opening_paren`

**Template:**
```python
result = some_function(arg1, arg2, arg3,
                      arg4, arg5)
```

### Log Message Rules

**Pattern:** `_LOG.{debug|info|warning|error}(...)`

**Algorithm:**
1. If entire call (format string + all args) fits in 100 chars → keep on one line
2. Otherwise, prefer moving ALL arguments to continuation lines
3. Exception: If moving all args adds extra line without benefit, keep some on first line

**Template:**
```python
# Preferred when message is long
_LOG.debug("Long message format string: %s, %s, %s",
           arg1, arg2, arg3)

# Acceptable when it saves a line
_LOG.debug("Long message: %s, %s, %s", arg1, arg2,
           arg3)
```

### String Splitting Rules

**Goal:** Maximize first line length (close to 100 chars) before natural break point

**Pattern for multi-line f-strings:**
```python
string = f"First part up to ~95-100 chars with natural break point " \
         f"continuation of the string"
```

**Anti-pattern:**
```python
# WRONG: First line too short when it could fit more
string = f"First part only 50 chars " \
         f"rest of the very long string here"
```

**Rules:**
- Use `\` for continuation
- Each continued line is its own f-string
- Align continuation lines with opening quote
- Break at natural boundaries (after complete phrases)

### Assert Rules

**Alignment:** `indent + 7` (for `assert ` keyword + space)

**Template:**
```python
    assert condition, \
           "Error message here"
```

## Comments & Documentation

### Comment Punctuation Rule

**MANDATORY:** All comments MUST end with period (`.`)

**Pattern Recognition:**
```regex
^\s*#.*[^.]$  # VIOLATION: Missing period
```

**Applies to:**
- Single-line comments: `# This is a comment.`
- Inline comments: `x = 5  # Set initial value.`
- Code example comments: `# Good: This works correctly.`
- Multi-line comment blocks (each line ends with period)

**Examples:**
- ✅ `# Good: All parameters fit on one line.`
- ✅ `# This is a comment.`
- ❌ `# Good: All parameters fit on one line`
- ❌ `# This is a comment`

### Message Capitalization Rule

**Pattern:** All log messages and exception messages

**Rules:**
1. Start with capital letter
2. After each `:` in message → capital letter
3. One-line messages: period optional
4. Multi-line messages: use periods

**Examples:**
- ✅ `_LOG.debug("Local: Read: CPU%d: MSR 0x%x", cpu, addr)`
- ✅ `raise Error(f"Failed to read: File not found")`
- ❌ `_LOG.debug("local: read: CPU%d", cpu)`
- ❌ `raise Error(f"failed to read file")`

### Docstring Rules

**Structure (mandatory order):**
1. One-line summary (imperative voice)
2. Blank line (if multi-line)
3. Args: (if has parameters besides self)
4. Returns: (if returns non-None)
5. Yields: (if generator)
6. Raises: (for public methods, optional for private)
7. Notes: (optional, bullet list format)

**Alignment in docstrings:**
- Continuation lines align at `colon_column + 2`

**Anti-pattern:**
```python
# WRONG: Declarative voice
"""This method returns the value."""

# CORRECT: Imperative voice  
"""Return the value."""
```

## Whitespace Rules

### Spaces Around Operators

**ALWAYS add spaces around:**
- Arithmetic: `+`, `-`, `*`, `/`, `//`, `%`, `**`
- Comparison: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Assignment: `=` (except in keyword arguments)

**Examples:**
- ✅ `result = value + 1`
- ✅ `func(name="value")`  # No spaces in keyword args
- ❌ `result = value+1`
- ❌ `func(name = "value")`  # Spaces in keyword args WRONG

### Dictionary Formatting

**Rule:** Spaces AFTER `:`, never before

**Pattern:**
```python
# Correct alignments
{"key": value}           # Small dict, one line
{"key":  value}          # Aligned values (spaces AFTER colon)
{"key": value}           # No alignment (no extra spaces)

# WRONG
{"key" : value}          # Spaces before colon - VIOLATION
```

## Type System Rules

### Immutable Collections

**Rule:** For module-level constants that are collections:
- Use `frozenset()` instead of `set()`
- Use `tuple()` instead of `list()`

**Pattern Recognition:**
```python
# Module-level constant (after _LOG definition, before class)
_CONSTANT_SET: Final[frozenset[str]] = frozenset({
    "item1",
    "item2",
})

# WRONG
_CONSTANT_SET: Final[set[str]] = {
    "item1", 
    "item2",
}
```

### Multi-line Frozenset Format

**Template:**
```python
_CONSTANT: Final[frozenset[str]] = frozenset({
    "value1",
    "value2",
    "value3",
})
```

**Rules:**
- Opening `frozenset({` on same line as variable
- One value per line
- Closing `})` on separate line, aligned with variable

## Import Rules

### Split Long Import Lines

**Rule:** Use multiple import statements, NOT parentheses

**Pattern:**
```python
# Correct
from module import Symbol1, Symbol2, Symbol3
from module import Symbol4

# WRONG  
from module import (Symbol1, Symbol2, Symbol3,
                   Symbol4)
```

**Decision:** If imports from same module don't fit in 100 chars → split into multiple lines

## File I/O Patterns (pepclibs specific)

### Using _sysfs_io

**Rule:** In pepclibs classes, ALL file operations use `self._sysfs_io`

**Patterns:**
- Read: `self._sysfs_io.read(path, what="description")`
- Write: `self._sysfs_io.write_verify(path, value, what="description")`
- Batch read: `self._sysfs_io.read_paths(paths_iter, what="description")`

**Anti-pattern:**
```python
# WRONG in pepclibs
with open(path) as f:
    content = f.read()

# WRONG in pepclibs  
self._pman.read_file(path)

# CORRECT in pepclibs
content = self._sysfs_io.read(path, what="file description")
```

## Common Anti-Patterns to Detect

### Anti-pattern 1: Incorrect Function Signature Split
```python
# WRONG
def method(self, param1: int,
           param2: str) -> bool:

# CORRECT
def method(self,
           param1: int,
           param2: str) -> bool:
```

### Anti-pattern 2: Missing Periods in Comments
```python
# WRONG
# This is a comment

# CORRECT
# This is a comment.
```

### Anti-pattern 3: Lowercase After Colons in Messages
```python
# WRONG
raise Error(f"Failed: file not found")

# CORRECT
raise Error(f"Failed: File not found")
```

### Anti-pattern 4: Dictionary with Spaces Before Colon
```python
# WRONG
{"key" : "value"}

# CORRECT
{"key": "value"}
```

### Anti-pattern 5: Using set() for Module Constants
```python
# WRONG
_CONSTANTS: Final[set[str]] = {"a", "b"}

# CORRECT
_CONSTANTS: Final[frozenset[str]] = frozenset({
    "a",
    "b",
})
```

### Anti-pattern 6: String Split Too Early
```python
# WRONG: First line only 60 chars when could fit 95
msg = f"Short message part " \
      f"that could have fit more on first line"

# CORRECT: First line ~95-100 chars
msg = f"Longer first line that fits more text up to natural break point " \
      f"continuation here"
```

### Anti-pattern 7: Hardcoded what= Parameters
```python
# WRONG: Hardcoded regardless of action
self._sysfs_io.write_verify(path, val, what="C-state disable")

# CORRECT: Dynamic based on action
action = "enable" if enable else "disable"
self._sysfs_io.write_verify(path, val, what=f"{action} C-state")
```

## Pre-Edit Validation Rules

Before making any edit, verify:

1. **Alignment Check:** Count exact column positions for signatures/calls
2. **Pattern Match:** Does existing code match expected patterns?
3. **Context Size:** Include 3-5 lines before/after for unique identification
4. **Whitespace Match:** Verify spaces/tabs match exactly

## Post-Edit Validation

After every edit:
1. Run `get_errors()` to check for type/syntax errors
2. Verify no unintended whitespace changes
3. Check that alignment calculations are correct
4. Ensure comment punctuation is preserved/added

## Priority Levels

**Critical (must fix):**
- Function signature alignment violations
- Type errors
- Missing comment periods
- Lowercase after colons in messages
- Spaces before colons in dictionaries

**High (should fix when touching code):**
- Mutable collections for constants (`set` → `frozenset`, `list` → `tuple`)
- Direct file I/O instead of `_sysfs_io` (in pepclibs)
- Hardcoded parameters that should be dynamic
- Imports with parentheses instead of multiple lines

**Medium (fix if convenient):**
- String splits that are too early
- Unnecessary splits when line fits in 100 chars

## Special Cases

### /proc/cmdline Reads (pepclibs/CPUIdle.py context)

**Pattern:** Best-effort diagnostic reads with warning on failure

**Template:**
```python
fpath = Path("/proc/cmdline")
try:
    cmdline = self._sysfs_io.read(fpath, what="kernel cmdline")
    for opt in cmdline.split():
        if opt == "cpuidle.off=1" or opt.startswith("idle="):
            return f"\nThe '{fpath}' file{self._pman.hostmsg} indicates that the '{opt}' " \
                   f"kernel boot parameter is set, this may be the reason"
except Error as err:
    _LOG.warning("Failed to read '%s'%s: %s", fpath, self._pman.hostmsg, err)
return ""
```

### Action Variables for Enable/Disable

**Pattern:** Use lowercase action variable, uppercase for logging

**Template:**
```python
if enable:
    val = "0"
    action = "enable"  # Lowercase
else:
    val = "1"
    action = "disable"  # Lowercase

_LOG.debug("%s C-state: CPU %d", action.upper(), cpu)  # Upper for logging
self._sysfs_io.write_verify(path, val, what=f"{action} C-state")  # Lower for what parameter
```

## Machine-Readable Patterns

### Pattern: Function Signature (Split Required)

**Trigger:** Line length > 100 OR return type is long

**Transform:**
```python
# Input
def long_method_name(self, param1: Type1, param2: Type2, param3: Type3 = default) -> ReturnType:

# Output  
def long_method_name(self,
                     param1: Type1,
                     param2: Type2,
                     param3: Type3 = default) -> ReturnType:
```

**Calculation:** 
- Base indent: 4 (if class method), 0 (if module function)
- Parameter column: `base_indent + 4 + len("method_name") + 1`

### Pattern: Module-Level Constant Collection

**Trigger:** Assignment with `set()`, `list()` at module level, after `_LOG` definition

**Transform:**
```python
# Wrong
_CONSTANTS = {"a", "b", "c"}

# Correct
_CONSTANTS: Final[frozenset[str]] = frozenset({
    "a",
    "b",
    "c",
})
```

### Pattern: Import Statement Too Long

**Trigger:** Import line > 100 chars

**Transform:**
```python
# Wrong
from module import Symbol1, Symbol2, Symbol3, Symbol4, Symbol5, Symbol6

# Correct
from module import Symbol1, Symbol2, Symbol3
from module import Symbol4, Symbol5, Symbol6
```

### Pattern: Comment Missing Period

**Trigger:** `^\s*#.*[^.]$`

**Transform:** Add `.` at end

```python
# Wrong
# This is a comment

# Correct
# This is a comment.
```

### Pattern: Dictionary with Space Before Colon

**Trigger:** `{\s*"[^"]+"\s+:` or `{\s*'[^']+'\s+:`

**Transform:**
```python
# Wrong
{"key" : value}
{"key"  : value}

# Correct
{"key": value}
{"key":  value}  # Extra spaces AFTER colon for alignment OK
```

### Pattern: Lowercase After Colon in Message

**Trigger:** Log/exception message contains `: [a-z]`

**Transform:** Capitalize letter after colon

```python
# Wrong
_LOG.debug("Failed: file not found")

# Correct
_LOG.debug("Failed: File not found")
```

## Context-Specific Rules

### CPUIdle.py Specific

1. **Cache Architecture:**
   - `_lsdir_cache`: Caches state directory names per CPU
   - `_sysfs_io`: Caches file contents
   - After direct writes: call `self._sysfs_io.cache_remove(path)`

2. **Iteration Order:**
   - Must be: cpus → states → files
   - Natural sort for state directories (state0, state1, ..., state10)

3. **File Operations:**
   - All reads: `self._sysfs_io.read(path, what=...)`
   - All writes: `self._sysfs_io.write_verify(path, val, what=...)`

### _SysfsIO.py Specific

**Note in docstrings:** Can be used for reading ANY files, not just sysfs

## Pre-Commit Validation Script

When reviewing code, check in this order:

1. **Function signatures** - alignment and splitting
2. **Comments** - all end with period
3. **Messages** - capitalization after colons
4. **Dictionaries** - spaces after colons only
5. **Imports** - no parentheses, multiple lines
6. **Constants** - frozenset/tuple for collections
7. **Strings** - first line close to 100 chars
8. **File I/O** - using _sysfs_io in pepclibs

## Examples of Complete Correct Patterns

### Example 1: Method with Proper Splitting

```python
    def _get_cstates_info(self,
                          cpus: Sequence[int],
                          csnames: Iterable[str] | Literal["all"]) -> \
                            Generator[tuple[int, dict[str, ReqCStateInfoTypedDict]], None, None]:
        """
        Retrieve and yield information about requestable C-states for given CPUs.

        Args:
            cpus: CPU numbers to get requestable C-states information for (the caller must validate
                  CPU numbers).
            csnames: Requestable C-state names to get information about.

        Yields:
            Tuples of (CPU number, C-state information dictionary).
        """
```

### Example 2: Helper Method with Best-Effort Diagnostic

```python
    def _format_idle_off_msg(self) -> str:
        """
        Format message about idle states disabled in kernel command line.

        Returns:
            Message fragment if relevant boot parameters found, empty string otherwise.
        """

        fpath = Path("/proc/cmdline")
        try:
            cmdline = self._sysfs_io.read(fpath, what="kernel cmdline")
            for opt in cmdline.split():
                if opt == "cpuidle.off=1" or opt.startswith("idle="):
                    return f"\nThe '{fpath}' file{self._pman.hostmsg} indicates that the '{opt}' " \
                           f"kernel boot parameter is set, this may be the reason"
        except Error as err:
            _LOG.warning("Failed to read '%s'%s: %s", fpath, self._pman.hostmsg, err)
        return ""
```

### Example 3: Module-Level Constants

```python
_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

# The C-state sysfs file names which are read by 'get_cstates_info()'.
_CST_SYSFS_FNAMES: Final[frozenset[str]] = frozenset({
    "name",
    "desc",
    "disable",
    "latency",
    "residency",
    "time",
    "usage",
})
```

### Example 4: Toggle Method with Dynamic Parameters

```python
    def _toggle_cstate(self, cpu: int, index: int, enable: bool):
        """
        Enable or disable a C-state for a given CPU.

        Args:
            cpu: The CPU number to enable or disable the C-state for.
            index: The index of the C-state to enable or disable.
            enable: If True, enable the C-state, otherwise disable it.
        """

        path = self._sysfs_base / f"cpu{cpu}" / "cpuidle" / f"state{index}" / "disable"
        if enable:
            val = "0"
            action = "enable"
        else:
            val = "1"
            action = "disable"

        _LOG.debug("%s C-state: CPU %d, state %d", action.upper(), cpu, index)

        try:
            self._sysfs_io.write_verify(path, val, what=f"{action} C-state")
        except (ErrorNotSupported, ErrorVerifyFailed) as err:
            raise Error(f"Failed to {action} C-state with index '{index}' for "
                        f"CPU {cpu}:\n{err.indent(2)}") from err
```

## Common Fixes Reference

| Violation | Pattern | Fix |
|-----------|---------|-----|
| Missing comment period | `# Comment$` | Add `.` at end |
| Lowercase after colon | `"Text: word"` | `"Text: Word"` |
| Space before dict colon | `{"key" :` | `{"key":` |
| set() constant | `_X = {"a"}` | `_X: Final[frozenset[str]] = frozenset({"a"})` |
| Multi-param same line | `def f(self, a: int,` | Split, one per line |
| String split too early | First line 60 chars | Extend to ~95-100 chars |
| Parenthesized imports | `from x import (A,` | `from x import A` + new line |
| Direct file read | `open(path)` or `pman.read_file()` | `self._sysfs_io.read(path, what=...)` |

## Validation Regex Patterns

Use these to detect violations:

```regex
# Comment without period (excluding special cases)
^\s*#[^#].*[^.]$

# Lowercase after colon in string
["'].*:\s+[a-z]

# Space before colon in dict
{\s*["'][^"']+["']\s+:

# Function signature with multiple params same line after split  
def \w+\([^,]+,\s*[^,]+,

# Multi-line import with parentheses
from .* import \(
```

## Decision Tree: When to Split Lines

```
Is line > 100 chars?
├─ NO → Keep on one line
└─ YES → What is it?
    ├─ Function signature?
    │   └─ Split: one param per line, aligned
    ├─ Function call?
    │   └─ Split: align at opening paren column
    ├─ Log message?
    │   └─ Split: prefer all args on continuation
    ├─ String literal?
    │   └─ Split: maximize first line (~95-100), then continue
    └─ Assert?
        └─ Split: align at indent + 7
```

---

**Note:** This document is optimized for AI processing. For detailed explanations and rationale, see [CONTRIBUTING.md](../CONTRIBUTING.md).
