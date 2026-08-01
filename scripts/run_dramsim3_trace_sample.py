#!/usr/bin/env python3
"""Run DRAMsim3 on a bounded prefix of a real emitted HBM transaction trace.

The result is deliberately labelled ``sampled_trace=true``.  It independently
validates timing behavior and address compatibility without claiming to replace
the exact full-trace Ramulator result or retaining multi-gigabyte text traces.
"""
from __future__ import annotations

import argparse
import os
import hashlib
import json
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=Path("tools/vendor/DRAMsim3/build/dramsim3main"))
    parser.add_argument("--config", type=Path, default=Path("tools/vendor/DRAMsim3/configs/HBM2_8Gb_x128.ini"))
    parser.add_argument("--max-lines", type=int, default=250_000)
    args = parser.parse_args()
    if args.max_lines <= 0:
        raise ValueError("max-lines must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sample = args.output.with_suffix(".trace")
    source_lines = sampled_lines = 0
    with args.trace.open() as source, sample.open("w") as target:
        for line in source:
            source_lines += 1
            fields = line.split()
            if not fields:
                continue
            address = fields[-1] if len(fields) > 1 else fields[0]
            target.write(f"{int(address, 0)}\n")
            sampled_lines += 1
            if sampled_lines >= args.max_lines:
                break
    try:
        # DRAMsim3's default CMake build leaves ``libdramsim3.so`` at the
        # repository root while ``dramsim3main`` lives in ``build/``.  Do not
        # rely on a host-wide ldconfig entry: this runner must remain portable
        # to the pinned, repository-local tool build used by the artifact.
        binary = args.binary.resolve()
        dramsim_root = binary.parent.parent
        env = os.environ.copy()
        library_path = str(dramsim_root)
        if env.get("LD_LIBRARY_PATH"):
            library_path += os.pathsep + env["LD_LIBRARY_PATH"]
        env["LD_LIBRARY_PATH"] = library_path
        result = subprocess.run(
            [str(binary), str(args.config.resolve()), "-c", "10000000", "-t", str(sample.resolve())],
            text=True, capture_output=True, timeout=900, env=env,
        )
        success = result.returncode == 0
        error = result.stderr[-1000:]
    except Exception as exc:  # audit artifact is still useful on tool failures
        success = False; result = None; error = str(exc)
    payload = {
        "tool": "DRAMsim3",
        "memory_model": args.config.stem,
        "source_trace": str(args.trace),
        "source_prefix_lines_seen": source_lines,
        "sample_lines": sampled_lines,
        "sampled_trace": True,
        "trace_sha256": hashlib.sha256(sample.read_bytes()).hexdigest(),
        "tool_run_success": success,
        "returncode": None if result is None else result.returncode,
        "error": error,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
