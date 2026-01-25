# Development Skills

This directory contains OpenCode skills that enforce best practices for this project.

## Skills

### 🧪 python-testing.md
**Rule:** Every code change requires full test suite run (`uv run pytest`)

### 💻 python-coding.md
**Rule:** Test-driven development with pre-commit checks

### 🚀 python-release.md
**Rule:** Full verification before any release

## Usage

These skills are automatically loaded by OpenCode when working on this project.

## The Core Principle

```
ANY CODE CHANGE → uv run pytest (full suite) → PASS → Commit
                                              → FAIL → Fix → Repeat
```
