# Workspace API

This directory owns the HTTP boundary of the active system. Domain logic remains in
`src/wgs_agent` and `src/wgs_fmt_platform`; this package only composes those capabilities
for the Next.js workspace.

Run from the repository root:

```bash
python -m uvicorn app.main:app --app-dir apps/workspace-api --port 8503
```
