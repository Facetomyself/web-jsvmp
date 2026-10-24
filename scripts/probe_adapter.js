/*
 * Runtime-neutral adapter sink for a target-specific VM hook.
 * It records supplied observations; it does not locate or hook an interpreter.
 * Browser callers should provide a bounded sink (e.g. chunk bridge), not console.
 */
class TraceAdapter {
  constructor({ runId, sourceSha256, vmId, sink, maxEvents = 100000 }) {
    if (!runId || !vmId || !/^[a-f0-9]{64}$/.test(sourceSha256 || "")) {
      throw new TypeError("runId, vmId and lowercase source SHA-256 are required");
    }
    if (typeof sink !== "function") throw new TypeError("sink callback is required");
    if (!Number.isSafeInteger(maxEvents) || maxEvents < 1) throw new TypeError("maxEvents must be a positive safe integer");
    this.runId = runId;
    this.sourceSha256 = sourceSha256;
    this.vmId = vmId;
    this.sink = sink;
    this.maxEvents = maxEvents;
    this.seq = 0;
    this.dropped = 0;
  }

  emit({ pc, opcode, operands, stackBefore, stackAfter, hostCalls = [], writes = [], branchTaken = null, timestampNs = null }) {
    if (this.seq >= this.maxEvents) {
      this.dropped += 1;
      return false;
    }
    if (!Number.isSafeInteger(pc) || pc < 0 || typeof opcode !== "string" || !opcode) {
      throw new TypeError("pc and opcode must be actual VM instruction observations");
    }
    if (![operands, stackBefore, stackAfter, hostCalls, writes].every(Array.isArray)) {
      throw new TypeError("operands/stack/side-effect fields must be arrays");
    }
    const row = {
      schema_version: 1,
      run_id: this.runId,
      source_sha256: this.sourceSha256,
      vm_id: this.vmId,
      seq: this.seq++,
      pc,
      opcode,
      operands,
      stack_before: stackBefore,
      stack_after: stackAfter,
      hostCalls,
      writes,
      branchTaken,
      timestampNs,
    };
    this.sink(row);
    return true;
  }

  receipt() {
    return { schema_version: 1, run_id: this.runId, source_sha256: this.sourceSha256, vm_id: this.vmId,
      emitted: this.seq, dropped: this.dropped, truncated: this.dropped > 0 };
  }
}

if (typeof module !== "undefined") module.exports = { TraceAdapter };
