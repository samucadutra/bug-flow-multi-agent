# BugFlow — Spec-Driven Development Kit

This folder contains everything you need to rebuild **BugFlow**, a multi-agent bug triage system, from scratch in a new English-only repository using **Spec-Driven Development (SDD)**.

## Start here

1. **[WALKTHROUGH.md](WALKTHROUGH.md)** is the detailed, step-by-step guide, written for SDD beginners. Keep it open while you work.
2. **[ORIGINAL-PROJECT-ANALYSIS.md](ORIGINAL-PROJECT-ANALYSIS.md)** (optional) explains what the original Portuguese project does, the defects found in it, and how these specs fix them.

## Contents

```
sdd-kit/
├── README.md                          ← this file
├── WALKTHROUGH.md                     ← step-by-step SDD guide (for you, the human)
├── ORIGINAL-PROJECT-ANALYSIS.md       ← analysis of the legacy project (reference only)
│
├── AGENTS.md                          ← operating rules for the AI coding assistant
├── CLAUDE.md                          ← tells Claude Code to load AGENTS.md
└── specs/
    ├── constitution.md                ← non-negotiable project principles
    ├── product-overview.md            ← vision, glossary, canonical enums, roadmap
    ├── _templates/                    ← blank templates for your own future features
    │   ├── spec-template.md
    │   ├── plan-template.md
    │   └── tasks-template.md
    ├── 001-project-foundation/        ← package, config, CLI, check, db init/seed
    │   ├── spec.md
    │   ├── plan.md
    │   └── tasks.md
    ├── 002-semantic-bug-index/        ← Pinecone embeddings, index and search
    ├── 003-triage-agents/             ← 4-agent CrewAI crew with structured outputs
    ├── 004-bug-reports/               ← Bug Documenter agent, Markdown/HTML reports
    └── 005-bug-reprocessing/          ← reopen command
```

Each feature folder has the same three files:

| File | Question it answers |
|---|---|
| `spec.md` | **What** must the feature do, and **why**? |
| `plan.md` | **How** will we build it? |
| `tasks.md` | In which **small, verifiable steps**? |

## What to copy into the new repository

| Copy to the new repo root | Keep outside the new repo |
|---|---|
| `AGENTS.md`, `CLAUDE.md`, `specs/` | `WALKTHROUGH.md`: you read it, the AI doesn't need it |
| | `ORIGINAL-PROJECT-ANALYSIS.md`: it quotes Portuguese identifiers that could leak into the new code |
| | `README.md`: the new project gets its own README in feature 001 |
