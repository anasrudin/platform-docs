# Docs

`memory-bank/` is the source of truth. `docs/` is the compact, reader-facing layer for humans who want the current shape without re-reading all 12 memory-bank files.

## Current Docs

| File | Purpose | Memory-bank sources |
|---|---|---|
| [runtime/platform-runtime-reference.md](./runtime/platform-runtime-reference.md) | Current runtime architecture, topology, MVP scope, and next milestones | `projectbrief.md`, `architecture-graph.md`, `runtime-topology.md`, `activeContext.md`, `progress.md`, `milestone-timeline.md` |
| [runtime/platform-runtime-roadmap.md](./runtime/platform-runtime-roadmap.md) | Current phased execution roadmap for the runtime build | `activeContext.md`, `milestone-timeline.md`, `progress.md` |
| [tools/platform-tools-reference.md](./tools/platform-tools-reference.md) | Current tool model, runtime tiers, skill routing, and registry snapshot | `tool-registry.md`, `systemPatterns.md`, `techContext.md`, `productContext.md` |
| [archive/legacy-kubernetes-reference.md](./archive/legacy-kubernetes-reference.md) | Historical K8s/GKE-era notes kept only for migration context | merged from prior archive docs |

## Rules

- Update the memory bank first when the architecture changes.
- Keep `docs/` short; link to memory-bank files instead of duplicating them.
- Archive superseded designs instead of keeping parallel "current" docs.
