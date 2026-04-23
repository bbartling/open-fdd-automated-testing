# Memory and secrets policy

## Commit to repo

Commit reusable knowledge such as:

- runbooks
- docs improvements
- report templates
- validation workflows
- non-secret deployment assumptions
- known pitfalls and recovery procedures

## Keep only in local memory

Keep private or local-only context out of git, including:

- bearer tokens and API keys
- `.env` contents
- JWT secrets
- personal notes that are not reusable repo knowledge
- raw session dumps with secrets or sensitive ops context

## Rule of thumb

If another future OpenClaw instance on another machine should know it, document it in repo docs.

If it is secret or user-private, keep it in local memory or local secure files.
