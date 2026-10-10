# Agent git rules (Cursor Agent, Claude, Copilot)

**Do not commit. Do not push.**

- Never run `git commit`, `git push`, or any equivalent (`gh pr create` that pushes, `git commit --amend`, force-push) unless the human **explicitly asked for that action in this turn**.
- Do not stage files “in case they want a commit.”
- Do not offer to commit or push unprompted.
- “Save the work,” “we’re done,” or “looks good” is **not** permission to commit or push.
- If they ask to commit later, wait for that message. Do not reuse an earlier yes.

**Never put Cursor, Claude, or any agent on GitHub contributors.**

- Do not add `Co-authored-by`, `Co-Authored-By`, `Made-with`, or `--trailer` for Cursor, Claude, Anthropic, or Copilot.
- Do not commit as `Cursor Agent`, `cursoragent@cursor.com`, or `noreply@anthropic.com`.
- Author and committer stay the human / repo `user.name`. The commit-msg hook strips agent trailers if the tool injects them.

Work in the tree. Leave `git status` dirty. The human owns the remote.

Paper drafts stay local: do not `git add` `writing/`, `paper_doc/`, `docs/TRIPOD_LLM_CHECKLIST.md`, or `docs/REVIEWER_PACKET.md`. They are gitignored. Tool docs in `docs/` (user guide, hosting, protocol) may stay tracked.
