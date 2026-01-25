# Python Release Skill

## Description
Use when creating releases for Python projects. Enforces full test suite, version bumping, and proper release workflow.

## MANDATORY RULES

### Rule 1: Full Test Suite Before Release
**NO release without 100% test pass rate.**

```bash
# REQUIRED before ANY release
uv run pytest

# REQUIRED: Check coverage
uv run pytest --cov --cov-report=term-missing

# All tests MUST pass
# Coverage MUST meet minimum threshold
```

### Rule 2: Version Bump Protocol
```bash
# 1. Run full test suite FIRST
uv run pytest

# 2. Update version in pyproject.toml
# version = "X.Y.Z"

# 3. Run full test suite AGAIN
uv run pytest

# 4. Commit version bump
git add pyproject.toml
git commit -m "chore: bump version to X.Y.Z"
```

### Rule 3: Release Checklist
```
[ ] All tests pass: uv run pytest
[ ] Coverage meets threshold: uv run pytest --cov
[ ] Version bumped in pyproject.toml
[ ] CHANGELOG updated (if applicable)
[ ] README updated (if applicable)
[ ] All changes committed
[ ] Tag created and pushed
[ ] GitHub release created
```

## Release Flow

```
┌─────────────────────────────────────────────────────────┐
│                  RELEASE PROCESS                        │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           STEP 1: RUN FULL TEST SUITE                   │
│                  uv run pytest                          │
│                                                         │
│   ❌ If ANY test fails → STOP, fix issues first         │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           STEP 2: CHECK COVERAGE                        │
│     uv run pytest --cov --cov-report=term-missing       │
│                                                         │
│   ❌ If coverage < threshold → STOP, add tests          │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           STEP 3: UPDATE VERSION                        │
│         Edit pyproject.toml: version = "X.Y.Z"          │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           STEP 4: RUN TESTS AGAIN                       │
│                  uv run pytest                          │
│                                                         │
│   ❌ If ANY test fails → STOP, fix issues               │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           STEP 5: BUILD PACKAGE                         │
│                    uv build                             │
│                                                         │
│   ❌ If build fails → STOP, fix issues                  │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           STEP 6: COMMIT & TAG                          │
│   git add pyproject.toml                                │
│   git commit -m "chore: bump version to X.Y.Z"          │
│   git tag -a vX.Y.Z -m "Release vX.Y.Z"                 │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           STEP 7: PUSH TO REMOTE                        │
│   git push origin main                                  │
│   git push origin vX.Y.Z                                │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           STEP 8: CREATE GITHUB RELEASE                 │
│   gh release create vX.Y.Z --title "..." --notes "..."  │
└─────────────────────────────────────────────────────────┘
```

## Version Numbering (Semantic Versioning)

### Format: MAJOR.MINOR.PATCH

| Change Type | Version Bump | Example |
|-------------|--------------|---------|
| Breaking changes | MAJOR | 1.0.0 → 2.0.0 |
| New features (backward compatible) | MINOR | 1.0.0 → 1.1.0 |
| Bug fixes | PATCH | 1.0.0 → 1.0.1 |

### Pre-release Versions
```
0.1.0-alpha.1
0.1.0-beta.1
0.1.0-rc.1
```

## Complete Release Commands

### Standard Release
```bash
# 1. Ensure clean working directory
git status  # Should be clean

# 2. Run full test suite
uv run pytest
# MUST show: "X passed"

# 3. Check coverage
uv run pytest --cov=<package> --cov-report=term-missing
# MUST meet coverage threshold

# 4. Update version in pyproject.toml
# Edit: version = "X.Y.Z"

# 5. Run tests again after version change
uv run pytest

# 6. Build package
uv build
# Should create dist/*.whl and dist/*.tar.gz

# 7. Commit version bump
git add pyproject.toml
git commit -m "chore: bump version to X.Y.Z"

# 8. Create annotated tag
git tag -a vX.Y.Z -m "Release vX.Y.Z

Features:
- Feature 1
- Feature 2

Fixes:
- Fix 1
- Fix 2

Tests: N passed, M% coverage"

# 9. Push to remote
git push origin main
git push origin vX.Y.Z

# 10. Create GitHub release
gh release create vX.Y.Z \
  --title "vX.Y.Z - Release Title" \
  --notes "## What's New

### Features
- Feature 1
- Feature 2

### Fixes
- Fix 1

### Installation
\`\`\`bash
pip install git+https://github.com/user/repo.git@vX.Y.Z
\`\`\`

### Tests
- N tests passing
- M% coverage"
```

### PyPI Release (Optional)
```bash
# After GitHub release, publish to PyPI
uv publish --token <PYPI_TOKEN>
```

## Release Notes Template

```markdown
## vX.Y.Z - Release Title

### Features
- Feature description

### Improvements
- Improvement description

### Bug Fixes
- Fix description

### Breaking Changes
- Breaking change description (MAJOR version only)

### Installation
\`\`\`bash
pip install package-name==X.Y.Z
# or
pip install git+https://github.com/user/repo.git@vX.Y.Z
\`\`\`

### Requirements
- Python >= 3.12
- Other requirements

### Tests
- X tests passing
- Y% code coverage
```

## Pre-Release Verification

### Automated Checks
```bash
# Run all quality checks
uv run pytest                    # Tests
uv run pytest --cov             # Coverage
uv run ruff check .             # Linting
uv run ruff format --check .    # Formatting
uv run mypy <package>           # Type checking
uv build                        # Build verification
```

### Manual Checks
```
[ ] README is up to date
[ ] All new features documented
[ ] Breaking changes documented
[ ] Examples work correctly
[ ] Installation instructions correct
```

## Anti-Patterns (FORBIDDEN)

```bash
# ❌ NEVER release without running tests
git tag v1.0.0 && git push origin v1.0.0  # Without pytest

# ❌ NEVER release with failing tests
# "Only 2 tests fail, it's fine" - NO

# ❌ NEVER release with decreased coverage
# "Coverage dropped 5%, but it's okay" - NO

# ❌ NEVER force push tags
git push --force origin v1.0.0  # DANGEROUS

# ❌ NEVER delete and recreate tags
git tag -d v1.0.0 && git tag v1.0.0  # Confusing
```

## Rollback Procedure

If a release has critical issues:

```bash
# 1. Do NOT delete the tag
# 2. Create a patch release immediately

# Fix the issue
# ... make fixes ...

# Run full test suite
uv run pytest

# Bump patch version
# version = "X.Y.Z+1"

# Release patch
git add -A
git commit -m "fix: critical issue in vX.Y.Z"
git tag -a vX.Y.Z+1 -m "Hotfix release"
git push origin main
git push origin vX.Y.Z+1

# Create GitHub release marking previous as deprecated
gh release create vX.Y.Z+1 --title "vX.Y.Z+1 - Hotfix" --notes "..."
```

## Release Frequency Guidelines

| Project Stage | Release Frequency |
|---------------|-------------------|
| Alpha (0.x.x) | As needed |
| Beta | Weekly/Bi-weekly |
| Stable (1.x.x+) | Monthly or on significant changes |
| Hotfix | Immediately when critical |
