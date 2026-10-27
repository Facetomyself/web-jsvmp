# Project evidence adapter

`scripts/project_adapter.py` is the only hosting boundary. It calls `jsvmp_toolchain.opcode_recovery` and nothing else. It does not start a browser, install packages, or copy the hosting validator.

```text
python scripts/project_adapter.py --source input.js --trace trace.ndjson --receipt collection.json --bytecode-hex HEX --fixture fixture.json --output-dir out --evidence-dir cas --gate gate.json --repo-root /path/to/host --node node
```

`--repo-root` is optional for a standalone run. With a hosting repository, the index gitlink must equal this checkout HEAD. Evidence production requires a clean skill checkout. There is no development bypass.

`--gate` must have `profile=jsvm-verifiable`, `next_skill=web-jsvmp`, and a source input whose SHA-256 matches `--source`. A mismatch returns before the pipeline runs.

On success the adapter writes `manifest.json` with `profile=jsvm-verifiable` and `claim_scope=partial`. The manifest has no `chain_accepted` and no `validation_scope`. Alignment failure, stack-effect mismatch, or fixture failure writes `adapter-receipt.json` with `status=insufficient-evidence` and does not write a manifest. `claim_scope=algorithm-recovered` is never produced here.

The hosting project validates that manifest with its own gate-bound validator. `ok=true` from this adapter is fixture-only parity inside the canonical ISA, not request parity or parent completion.
