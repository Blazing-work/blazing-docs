# Internal Developer References

This folder contains internal documentation for Blazing developers. For public documentation, see the [docs/](../docs/) folder.

## Structure

```
references/
├── LEXICON.md                    # Source of truth for v2.0 terminology
├── PRODUCT_NAMING.md             # Product naming conventions
├── lexicon-v2-*.md               # Lexicon migration tracking
│
├── architecture/                 # System design & implementation
│   ├── architecture.md           # High-level architecture overview
│   ├── EXECUTOR_ARCHITECTURE.md  # Executor/Coordinator design
│   ├── crdt-multimaster-queues.md # CRDT queue implementation
│   └── ...
│
├── security/                     # Security documentation
│   ├── security-dynamic-code-execution.md
│   ├── dill-deserialization-security-validation.md
│   └── ...
│
├── debugging/                    # Debugging guides & journals
│   ├── troubleshooting.md
│   ├── debugging-journal-dynamic-code.md
│   └── ...
│
├── testing/                      # Testing documentation
│   ├── testing.md
│   ├── benchmarking.md
│   └── ...
│
├── proposals/                    # Historical proposals & evaluations
│   ├── pyron-evaluation.md
│   ├── service_versioning_proposal.md
│   └── ...
│
├── legacy/                       # Outdated docs (kept for reference)
│   ├── developer-guide.md        # Superseded by public docs
│   ├── web-endpoints.md          # Superseded by blazing-flow-endpoint
│   └── ...
│
└── docs/examples/                     # Internal example scripts
    ├── dynamic_code_execution.py
    └── ...
```

## Key Documents

| Document | Purpose |
|----------|---------|
| `LEXICON.md` | Canonical terminology mapping (v1 → v2) |
| `architecture/architecture.md` | System architecture overview |
| `architecture/EXECUTOR_ARCHITECTURE.md` | 4 worker types, sandbox isolation |
| `security/security-dynamic-code-execution.md` | Dynamic code security model |

## Public Documentation

For user-facing documentation, see:
- `docs/` - Documentation website content (submodule)
- `docs/examples/` - User examples & tutorials (submodule)
