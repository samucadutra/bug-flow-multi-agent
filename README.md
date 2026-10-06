# BugFlow

BugFlow is a multi-agent bug triage system. This repository is built with Spec-Driven
Development: the documents in `docs/` are the source of truth.

This README is a stub. The full quickstart is written in a later feature (F15).

## Layout

- `backend/` - Python project (uv, package `bugflow`)
- `docs/` - PRD, specs, plans and contracts
- `scripts/` - helper scripts, including `resolve-env.sh` for per-worktree isolation
- `docker-compose.yml` - local Postgres with pgvector
- `.env.example` - environment variable contract (copy to `.env`)
