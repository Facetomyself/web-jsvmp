# Optional phase artifact contracts

`phase_contracts.py` defines additive, producer-neutral envelopes for three
optional analysis phases: `symexec`, `irfix`, and `wasm-stage9`. They are
evidence records, not a second case lifecycle. They do not change the parent
dispatcher, the existing `jsvmp_toolchain.py` commands, the trace schema, or
the shared manifest contract.

These interfaces record which inputs and outputs a tool claims to have used.
They do not implement a symbolic executor, an IR transformation engine, a
WebAssembly analyzer, or a semantic equivalence checker. A passing record
validation means only that the record is well-formed and its declared digest
links are consistent.

## Common record

The JSON contract is [phase-artifact.schema.json](../schemas/phase-artifact.schema.json).
The Python validator adds cross-field checks that JSON Schema alone does not
express, including role uniqueness and digest-link consistency.

```json
{
  "schema_version": 1,
  "phase": "symexec",
  "status": "partial",
  "claim_scope": "artifact-only",
  "inputs": [
    {"role": "source", "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
    {"role": "trace", "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}
  ],
  "tool": {"name": "external-tool", "version": "1.0", "code_sha256": null},
  "outputs": [
    {"role": "ir", "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}
  ],
  "evidence": [],
  "details": {"trace_status": "unknown", "event_count": 0, "ir_format": "ir-v1"},
  "limitations": ["Unobserved paths are outside this artifact's claim scope."]
}
```

Each input, output, and evidence item has a unique role and a lowercase
SHA-256 digest. `tool.code_sha256` is either the digest of the relevant tool
implementation/configuration or `null` when that digest cannot be supplied;
the tool name and version remain required. A `blocked` record has no outputs.
Other statuses require at least one output. All records state at least one
limitation.

## Phase-specific fields

| Phase | Required inputs / output | `details` | Narrow claim ceiling |
|---|---|---|---|
| `symexec` | `source` + `trace` inputs; `ir` output | `trace_status`, `event_count`, `ir_format` | `artifact-only`; `trace-alignment-only` additionally requires `trace_status=verified` and a `trace-alignment-report` evidence digest |
| `irfix` | `ir` input and output | input IR digest, rules digest, pass identifiers, parity status/report digest, idempotence status | `artifact-only`; `fixture-only` requires a passed parity report whose digest is listed as evidence |
| `wasm-stage9` | `module` input | module digest, producer-defined nonempty route identifier, parity status/report digest | `artifact-only`; `fixture-only` requires a passed parity report whose digest is listed as evidence |

For IR correction, `input_ir_sha256` must equal the declared `ir` input digest.
For WebAssembly work, `module_sha256` must equal the declared `module` input
digest. A failed or unrun parity check cannot be promoted to `fixture-only`.
The `fixture-only` label applies only to the cited fixtures; it does not imply
whole-program, all-path, browser, or service equivalence.

When these phases are chained, preserve each phase record and bind each
downstream `ir` input digest to the preceding output digest. If an input, tool,
rule set, or parameter changes, generate a new output and a new record rather
than reusing a stale report. The validator deliberately does not infer
unreported source provenance or decide whether a transformation preserves
JavaScript side effects.

## Validation interface

The library entry point is `validate_record(value)`. The additive CLI is:

```sh
python scripts/phase_contracts.py <record.json>
```

Exit `0` returns a compact validation receipt; contract or I/O errors return
`2` and a JSON error on stderr. A successful receipt does not replace the
existing opcode gate, fixture runner, shared host validator, or business-level
readback. Keep the existing `normalize`, `decode`, `lift`, `align`, and `run`
interfaces unchanged.

## Stage 9 as a bounded WebAssembly branch

`wasm-stage9` is an optional phase record attached to the existing
`opcode-recovery` work, not a new `jsvmBlocker`, case state, or dispatch route.
Use the record to pin the module digest, the chosen type of work, generated
artifacts, and any bounded parity evidence. Preserve the original module as an
input reference. A text translation, import/export listing, or execution
observation is evidence of that artifact or boundary only; do not elevate it
into recovered algorithm semantics without separately recorded validation.
