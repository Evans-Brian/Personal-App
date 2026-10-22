# Working on this app

After completing requested app changes, run relevant checks, review the staged diff for private data, commit, and push to the configured GitHub remote by default. The user has explicitly authorized this workflow; do not ask again for routine pushes. Never force-push or overwrite unrelated remote changes. If authentication or a failed check blocks the push, report it accurately.

Publish application source, tests, and documentation only. Never commit databases, journal/vault content, people or restaurant records, browser drafts, backups, local settings, credentials, tokens, or generated runtime files. Keep .gitignore current and inspect staged paths before committing. Do not modify synced project sources outside this app.

Read the ignored `PRIVATE_CONTEXT.md`, when present, before interpreting journal or sleep data. It contains private terminology and analysis preferences for this user; keep its contents out of commits and public documentation.
