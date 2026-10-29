# Integrated CLI journey construction review — 2026-10-27

B-lineage construction only, runtime unverified; never independent Q acceptance.
Original base f57ede3; accepted DL1 d77daaa and INT dictionary contract correction
subsequently fast-forwarded from master to 3f6df71 while preserving owned edits.
No API signature change required: dictionary is consumed unchanged, including site_id,
derived tables/bindings and string report_code. Paired inverse remains a builder
projection, not a Java/generic-RT pass; the runtime roundtrip command still refuses.

Fresh Medium reviewer 0019_Codex_gpt-61-sol_Sub_DL4JourneyReview source-traced actual
producer signatures, literal success names, ledger closure, simulated rulings, complete
escaped reporting and evaluation refusal. Required corrections were journal/lock mutual
aliases, SQLite sidecar/input aliases, unsupported parser atom exit status and deeply
nested JSON errors. Those were corrected before handoff.

Fresh High reviewer 0021_Codex_gpt-61-sol_Sub_DL4JourneyHigh passed journal aliases,
atom-level refusal and JSON depth/error handling. It found a further canonical-sidecar
gap for ledger filename symlinks. The CLI now resolves the database path, checks that
path and its -journal/-wal/-shm sidecars against explicit inputs and pairwise aliases,
and passes that same returned path to all three Ledger constructors.

Fresh Xhigh reviewer 0023_Codex_gpt-61-sol_Sub_DL4LedgerXhigh returned PASS for that
narrow final correction, including rejection of :memory: before path resolution.
No required finding remains. Effort returns to Medium after that pass.

DL static evidence: three Python source ASTs parsed, changed CLI re-parsed after fixes,
staged git diff --check passed, accepted producer source/dictionary hash call paths and
external evaluation exclusion traced. No imports/application execution, tests, installs,
builds, Java, services, network or models. No fake signatures/expectations/held-out data.

Deferred: installed CLI/Typer, supported/partial/refused exits, full developer journey,
same-release dictionary hash agreement, mock attempts/unknown usage/persistence, journal
CAS/durability/alias negatives, HTML injection and real Windows filesystem race/locking
semantics. Guards inspect existing paths; no race-proof filesystem containment claim.

UPDATE005 follow-up: reviewed 825b7f2 preserved; accepted c6cc5b2 runner/archive source
merged at d7901fd7460bd0907b8884fe071192019cc25726. No evaluation import added to src.
PORTS005 requires new simulation journals; CLI now rejects an existing journal or lock,
including dangling symlinks, before store access. Fresh Medium reviewer
0024_Codex_gpt-61-sol_Sub_DL4PortsReview returned PASS on this bounded delta and docs:
explicit simulation retained, JSON error/exit 1 on existing paths, one new journal
record per CLI action, replay retains prior behavior. AST and staged whitespace checks
passed. Provisional DL2 as-built port guidance read; consumed common signatures match
the accepted baseline, optional legacy site_id remains unexposed pending a pinned port.
