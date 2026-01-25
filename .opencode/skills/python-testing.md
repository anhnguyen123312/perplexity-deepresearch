# Python Testing Skill

## Description
Use when running tests for Python projects. Enforces full test suite execution on every change.

## MANDATORY RULES

### Rule 1: ALWAYS Run Full Test Suite
**Every code change (add, modify, delete) MUST run the complete test suite.**

```bash
# REQUIRED after ANY code change
uv run pytest

# With coverage (recommended)
uv run pytest --cov --cov-report=term-missing
```

### Rule 2: NO Partial Test Runs in CI/Commit Flow
- ❌ `pytest tests/test_one_file.py` - FORBIDDEN for final verification
- ❌ `pytest -k "specific_test"` - FORBIDDEN for final verification  
- ✅ `uv run pytest` - REQUIRED before any commit

### Rule 3: Test Verification Checklist
Before marking any task complete:
```
[ ] Full test suite run: `uv run pytest`
[ ] All tests passing: 100%
[ ] No new warnings introduced
[ ] Coverage maintained or improved
```

## Test Execution Flow

### 1. During Development (Iterative)
```bash
# OK to run specific tests while developing
uv run pytest tests/test_specific.py -v

# OK to run with keyword filter while debugging
uv run pytest -k "test_function_name" -v
```

### 2. Before Commit (MANDATORY)
```bash
# MUST run full suite
uv run pytest

# MUST check coverage
uv run pytest --cov=<package_name> --cov-report=term-missing

# MUST verify no regressions
# Expected: All tests pass, coverage >= previous
```

### 3. After Any File Change
```bash
# After adding new file
uv run pytest

# After modifying existing file
uv run pytest

# After deleting file
uv run pytest

# After changing dependencies
uv sync && uv run pytest
```

## Test Output Verification

### Success Criteria
```
===== X passed in Y.YYs =====
```
- X must equal total test count
- No failures, errors, or skips (unless intentional)

### Failure Response
If tests fail:
1. DO NOT commit
2. Fix the failing tests
3. Run full suite again
4. Repeat until 100% pass

## Coverage Requirements

### Minimum Thresholds
- New code: 80% coverage minimum
- Overall project: Maintain or improve existing coverage
- Critical paths: 100% coverage

### Coverage Commands
```bash
# Basic coverage
uv run pytest --cov=<package>

# With missing lines
uv run pytest --cov=<package> --cov-report=term-missing

# HTML report
uv run pytest --cov=<package> --cov-report=html
```

## Pre-Commit Checklist

```markdown
## Before Every Commit
- [ ] `uv run pytest` - ALL tests pass
- [ ] `uv run pytest --cov` - Coverage maintained
- [ ] No new test warnings
- [ ] Test count same or increased
```

## Anti-Patterns (FORBIDDEN)

```bash
# ❌ NEVER commit with partial test run
git add . && git commit -m "fix"  # Without running pytest first

# ❌ NEVER skip tests
pytest --ignore=tests/slow_tests/

# ❌ NEVER commit with failing tests
# "I'll fix it later" - NO

# ❌ NEVER reduce coverage without justification
# Deleting tests to make suite pass - NO
```

## Integration with Git

### Pre-commit Hook (Recommended)
```bash
#!/bin/sh
# .git/hooks/pre-commit
uv run pytest || exit 1
```

### Commit Message Format
```
type(scope): description

- Change 1
- Change 2

Tests: X passed, Y% coverage
```
