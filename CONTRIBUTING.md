# Contributing to SalesScope

## Branch workflow

- Keep `main` stable.
- Use one branch for one feature or one closely related feature group.
- Use branch names such as `feature/upload-validation` or `fix/weekly-period`.
- Do not add an unrelated feature to an active branch.
- Open a pull request after the branch checks pass.

## Commit scale

Commit after a coherent, validated unit of work.

### Small commit

Use for one focused correction that can be reviewed alone:

- correct a label or error message;
- add one missing validation rule;
- fix one calculation;
- add one focused test.

### Feature commit

Use when one user-visible behavior works from start to finish:

- upload a file;
- map columns;
- display a data-quality receipt;
- calculate one weekly metric;
- add one report breakdown.

### Supporting commit

Keep tests, documentation, or infrastructure separate when they form a clear review boundary:

- add verification for a completed feature;
- document a product decision or workflow;
- add CI, formatting, or dependency configuration.

## When to commit

Create a commit when all of these conditions are true:

1. The change has one clear purpose.
2. The relevant behavior works.
3. The relevant tests, build, and lint checks pass.
4. The diff does not include unrelated work.
5. The commit message explains the result.

Do not wait until several major features are complete. Do not create a commit for every saved file or unfinished experiment.

## Commit messages

Use a short Conventional Commit prefix:

```text
feat: add column mapping review
fix: use the latest complete reporting week
test: verify Excel sheet selection
docs: explain partial analysis behavior
chore: configure frontend dependencies
```

## Before pushing

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm.cmd run build
npm.cmd run lint
```

Review the branch before pushing:

```powershell
git status
git diff --check
git log --oneline --decorate -10
```

## Data policy

Do not commit the full Kaggle ZIP, raw CSV files, user uploads, temporary analysis files, or files containing customer personal information.

Keep:

- small test fixtures;
- reproducible data-generation or audit scripts;
- notebooks that explain validated findings;
- instructions for downloading public source data.
