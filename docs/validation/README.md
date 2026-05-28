# docs/validation/

This directory contains the knowledge-graph validation artefacts for the TOW Companion project.

The **tracker** (`graph-validation-tracker.md`) drives a repeatable agentic validation flow:
52 items covering parse-contract foundations (F01–F06), all 17 node types (N01–N17), and all 29
tracked edge/relation types (E01–E29). Agents run one item at a time; conformity reports land in
`conformity/<ID>-<slug>.md`.

## How to launch a validation run

Spawn a general-purpose agent with this prompt (or paste it into Claude Code directly):

```
Read docs/validation/graph-validation-tracker.md fully, then follow the Agent Protocol
at the top of that file to validate the first pending item. Use docs/warhammer_tow_domain_knowledge.md
as the domain reference. This is a read-only task except for writing the conformity report and
marking the item done in the tracker. Do not start a second item.
```

Repeat until all boxes in the Item Index are checked.

## Files

| File | Purpose |
|---|---|
| `graph-validation-tracker.md` | Master tracker — protocol, index, and 52 item detail blocks |
| `conformity/` | Output dir for per-item conformity reports written by agents |
