---
name: commit-format
description: Use when creating, amending, rewriting, squashing, or reviewing git commit messages in this chezmoi repository, especially after a user asks to commit, says the commit format is wrong, or requests repository history consistency.
---

# Commit Format

## Overview

Use this repository's commit history as the source of truth before writing any commit message. This chezmoi repository uses Conventional Commits.

## Required Workflow

1. Before running `git commit`, `git commit --amend`, or equivalent history edits, inspect recent history:

```bash
git log --oneline -20
```

2. Write commit messages in this shape:

```text
type(scope): lowercase imperative summary
type: lowercase imperative summary
```

Use a scope when recent history uses scopes for similar files or subsystems.

3. If the most recent commit message is wrong and the user asks to fix or submit the current work, amend that commit instead of adding a new formatting-only commit, unless the user explicitly wants a separate commit.

## Quick Reference

| Change | Message shape |
| --- | --- |
| Bug fix | `fix(scope): summary` |
| New capability or configuration | `feat(scope): summary` |
| Maintenance or generated metadata | `chore(scope): summary` |
| Formatting-only change | `style(scope): summary` |
| Documentation-only change | `docs(scope): summary` |
| Refactor without behavior change | `refactor(scope): summary` |

## Local Examples

Recent valid examples:

```text
feat(codex): move defaults to profile
fix: use chat completions for notify voice
chore: ignore codex files
```

## Red Flags

Stop and re-check history when about to use:

- Title case summaries like `Fix pnpm global bin path`
- Vague messages like `update`, `changes`, or `misc`
- Missing type prefixes
- A separate commit whose only purpose is to fix the previous commit message
