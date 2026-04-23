# OpenClaw handoff protocol for Open-FDD

Use this when multiple agents, sessions, or humans are handing work across the same repo.

## Goals

- keep findings durable
- keep secrets out of git
- reduce repeated rediscovery
- make next-session startup fast and safe

## Always record

- current branch and commit SHA
- API base URL used
- auth mode used
- whether this was test bench or live HVAC
- whether writes were allowed
- exact endpoints exercised
- exact regressions or mismatches found
- smallest next fix

## Preferred durable locations

- `reports/` for timestamped test and validation artifacts
- `repo_reviews/` for branch/repo status snapshots
- docs pages for lessons that will matter again

## Handoff message shape

Keep handoffs short and concrete:

1. goal
2. current state
3. what was proved
4. what is blocked
5. exact next step

## Secrets rule

Do not paste `.env` secrets, bearer tokens, JWTs, or private auth files into committed handoff artifacts.

## Reset/bootstrap nuance

If `bootstrap.sh` or Docker orchestration must run in a different container or host context, the human may need to execute that step. In that case:

1. ask the human to run the command in the correct environment
2. verify outcomes afterward via API
3. record clearly whether proof is direct-log proof or API-side postcondition proof
