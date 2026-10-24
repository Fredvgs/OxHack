# .claude/: Claude Code settings for this repo (shared with the team)

| File | What it does |
|---|---|
| `settings.json` | Lets Claude run `uv run ...`, read-only git and `git add` without asking. Always asks before `git commit`. Blocks `git push --force` and `rm -rf`. Turns off "Co-Authored-By" lines. Runs the format hook below. |
| `hooks/ruff_format.py` | After Claude edits a `.py` file, formats it with ruff. Never blocks. |

Project instructions for Claude are in `CLAUDE.md` at the repo root. Personal settings go in
`.claude/settings.local.json`, and personal notes in `CLAUDE.local.md`; both are gitignored.
