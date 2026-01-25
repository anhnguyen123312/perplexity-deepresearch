# Python Coding Skill

## Description
Use when writing or modifying Python code. Enforces test-driven development and full test suite verification.

## MANDATORY RULES

### Rule 1: Every Change Requires Full Test Run
**No exceptions. Every add, modify, or delete MUST be followed by:**

```bash
uv run pytest
```

### Rule 2: Test-First Development
1. Write/update tests FIRST
2. Run tests (should fail for new features)
3. Implement code
4. Run full test suite
5. All tests must pass before commit

### Rule 3: Change Verification Flow

```
┌─────────────────────────────────────────────────────────┐
│                    CODE CHANGE                          │
│         (Add / Modify / Delete any .py file)            │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              RUN FULL TEST SUITE                        │
│                  uv run pytest                          │
└─────────────────────────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
        ┌──────────┐             ┌──────────┐
        │  PASS    │             │  FAIL    │
        └──────────┘             └──────────┘
              │                         │
              ▼                         ▼
        ┌──────────┐             ┌──────────┐
        │  COMMIT  │             │   FIX    │
        └──────────┘             └──────────┘
                                       │
                                       └──────► (back to RUN TESTS)
```

## Code Quality Checklist

### Before Writing Code
```
[ ] Understand the requirement
[ ] Identify affected tests
[ ] Plan test cases for new functionality
```

### After Writing Code
```
[ ] Run: uv run pytest (FULL SUITE)
[ ] All tests pass
[ ] No type errors: uv run mypy <package>
[ ] Code formatted: uv run ruff format .
[ ] Linting clean: uv run ruff check .
```

### Before Commit
```
[ ] Full test suite: uv run pytest ✓
[ ] Coverage check: uv run pytest --cov ✓
[ ] Type check: uv run mypy <package> ✓
[ ] Format check: uv run ruff format --check . ✓
[ ] Lint check: uv run ruff check . ✓
```

## File Change Rules

### Adding New File
```bash
# 1. Create the file
touch package/new_module.py

# 2. Create corresponding test file
touch tests/test_new_module.py

# 3. Write tests first
# Edit tests/test_new_module.py

# 4. Run tests (should fail)
uv run pytest tests/test_new_module.py

# 5. Implement the module
# Edit package/new_module.py

# 6. Run FULL test suite
uv run pytest  # <-- MANDATORY

# 7. Verify all pass, then commit
```

### Modifying Existing File
```bash
# 1. Identify affected tests
grep -r "import module_name" tests/

# 2. Update tests if needed
# Edit tests/test_module.py

# 3. Make code changes
# Edit package/module.py

# 4. Run FULL test suite
uv run pytest  # <-- MANDATORY

# 5. Verify all pass, then commit
```

### Deleting File
```bash
# 1. Find all references
grep -r "from package import module" .

# 2. Update/remove dependent code

# 3. Update/remove tests

# 4. Delete the file
rm package/module.py

# 5. Run FULL test suite
uv run pytest  # <-- MANDATORY

# 6. Verify all pass, then commit
```

## Import and Dependency Rules

### Adding New Dependency
```bash
# 1. Add to pyproject.toml
uv add new-package

# 2. Sync environment
uv sync

# 3. Run FULL test suite
uv run pytest  # <-- MANDATORY

# 4. Verify compatibility
```

### Removing Dependency
```bash
# 1. Find all usages
grep -r "import package" .
grep -r "from package" .

# 2. Remove usages from code

# 3. Remove from pyproject.toml
uv remove package

# 4. Sync environment
uv sync

# 5. Run FULL test suite
uv run pytest  # <-- MANDATORY
```

## Error Handling

### When Tests Fail
1. **DO NOT** commit with failing tests
2. **DO NOT** skip or ignore failing tests
3. **DO** fix the issue
4. **DO** run full suite again
5. **DO** repeat until 100% pass

### When Adding Exception Handling
```python
# Always test exception paths
def test_function_raises_on_invalid_input():
    with pytest.raises(ValueError):
        function_under_test(invalid_input)
```

## Code Style Enforcement

### Required Tools
```bash
# Format code
uv run ruff format .

# Check linting
uv run ruff check .

# Fix auto-fixable issues
uv run ruff check --fix .

# Type checking
uv run mypy <package>
```

### Pre-Commit Sequence
```bash
# Run in this order
uv run ruff format .
uv run ruff check --fix .
uv run mypy <package>
uv run pytest  # <-- ALWAYS LAST, ALWAYS FULL
```

## Anti-Patterns (FORBIDDEN)

```python
# ❌ NEVER commit untested code
def new_function():
    pass  # "I'll add tests later"

# ❌ NEVER skip tests
@pytest.mark.skip("Broken, will fix later")
def test_something():
    pass

# ❌ NEVER catch and ignore exceptions silently
try:
    risky_operation()
except:
    pass  # Swallowing errors

# ❌ NEVER use print for debugging in committed code
print("DEBUG:", value)  # Remove before commit
```

## Commit Standards

### Message Format
```
type(scope): brief description

- Detailed change 1
- Detailed change 2

Tests: X passed, Y% coverage
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code restructuring
- `test`: Test changes only
- `docs`: Documentation
- `chore`: Maintenance

### Example
```
feat(cookies): add keychain password prompt

- Add prompt_keychain_password() function
- Integrate with extract_cookies_with_relaunch()
- Handle password cancellation gracefully

Tests: 115 passed, 97% coverage
```
