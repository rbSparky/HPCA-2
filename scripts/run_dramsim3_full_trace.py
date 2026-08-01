#!/usr/bin/env python3
"""Run pinned DRAMsim3 over a complete emitted Ramulator address trace.

The Ramulator traces contain an operation token followed by a hexadecimal
address.  DRAMsim3's trace reader consumes ``address operation cycle`` records,
so the conversion is streamed into a temporary file and removed after the run.
No prefix cap is applied; the JSON records the exact source and converted line
counts, hashes, command, and tool output tails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--trace", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--binary", type=Path, default=Path("tools/vendor/DRAMsim3/build/dramsim3main"))
    p.add_argument("--config", type=Path, default=Path("tools/vendor/DRAMsim3/configs/HBM2_8Gb_x128.ini"))
    p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("--cycles", type=int, default=10_000_000)
    p.add_argument("--arrival-cycle", type=int, default=0, help="constant cycle stamped on each request; ignored when --arrival-stride is nonzero")
    p.add_argument("--arrival-stride", type=int, default=0, help="stamp request i at i*stride cycles; use 1 for a causal one-request-per-cycle feeder")
    p.add_argument("--capacity-bytes", type=int, default=8 * 1024**3, help="HBM address capacity; trace addresses are wrapped into this legal range")
    p.add_argument("--keep-converted", action="store_true", help="retain the generated DRAMsim3 trace for audit/debug")
    args = p.parse_args()
    source = args.trace.resolve(); binary = args.binary.resolve(); config = args.config.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    source_lines = 0
    converted_lines = 0
    start = time.monotonic()
    error = ""
    stdout_tail = ""
    stderr_tail = ""
    returncode: int | None = None
    sim_ok = False
    with tempfile.NamedTemporaryFile(prefix="dramsim3_full_", suffix=".trace", mode="w", delete=False) as tmp:
        converted = Path(tmp.name)
        with source.open(errors="replace") as fh:
            for line in fh:
                source_lines += 1
                fields = line.split()
                if not fields:
                    continue
                token = fields[1] if len(fields) > 1 else fields[-1]
                try:
                    address = int(token, 0)
                except ValueError:
                    continue
                op = fields[0].upper() if fields else "LD"
                dram_op = "WRITE" if op in {"ST", "STORE", "WRITE", "P_MEM_WR", "BOFF"} else "READ"
                mapped = address % args.capacity_bytes
                arrival = converted_lines * args.arrival_stride if args.arrival_stride else (args.arrival_cycle if args.arrival_cycle else 0)
                tmp.write(f"0x{mapped:x} {dram_op} {arrival}\n")
                converted_lines += 1
    stats_dir = Path(tempfile.mkdtemp(prefix="dramsim3_stats_"))
    served_reads = served_writes = reported_cycles = 0
    try:
        env = os.environ.copy()
        root = binary.parent.parent
        env["LD_LIBRARY_PATH"] = str(root) + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
        command = [str(binary), str(config), "-c", str(args.cycles), "-o", str(stats_dir), "-t", str(converted)]
        proc = subprocess.run(command, text=True, capture_output=True, timeout=args.timeout, env=env)
        returncode = proc.returncode
        stdout_tail = proc.stdout[-4000:]
        stderr_tail = proc.stderr[-4000:]
        sim_ok = proc.returncode == 0
        if not sim_ok:
            error = f"returncode={proc.returncode}"
        stats = stats_dir / "dramsim3.txt"
        if stats.exists():
            import re
            text = stats.read_text(errors="replace")
            served_reads = sum(int(v) for v in re.findall(r"num_reads_done\s*=\s*(\d+)", text))
            served_writes = sum(int(v) for v in re.findall(r"num_writes_done\s*=\s*(\d+)", text))
            cycles = [int(v) for v in re.findall(r"num_cycles\s*=\s*(\d+)", text)]
            reported_cycles = max(cycles) if cycles else 0
    except subprocess.TimeoutExpired as exc:
        error = f"timeout_after_seconds={args.timeout}"
        stdout_tail = str(exc.stdout or "")[-4000:]
        stderr_tail = str(exc.stderr or "")[-4000:]
    except Exception as exc:
        error = repr(exc)
    finally:
        if not args.keep_converted:
            converted.unlink(missing_ok=True)
    payload = {
        "tool": "DRAMsim3",
        "memory_model": config.stem,
        "source_trace": str(source),
        "source_trace_sha256": sha(source),
        "source_lines": source_lines,
        "converted_lines": converted_lines,
        "sampled_trace": False,
        "complete_trace": converted_lines == source_lines,
        "trace_sha256": sha(source),
        "address_mapping": "modulo_capacity_bytes",
        "capacity_bytes": args.capacity_bytes,
        "arrival_mode": "sequential_stride" if args.arrival_stride else "constant",
        "arrival_stride": args.arrival_stride,
        "converted_trace_retained": bool(args.keep_converted),
        "tool_run_success": sim_ok,
        "reported_dram_cycles": reported_cycles,
        "served_reads": served_reads,
        "served_writes": served_writes,
        "served_requests": served_reads + served_writes,
        "all_requests_served": (served_reads + served_writes) >= converted_lines,
        "returncode": returncode,
        "command": command if 'command' in locals() else [],
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "error": error,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("source_lines", "converted_lines", "complete_trace", "tool_run_success", "elapsed_seconds", "error")}, sort_keys=True))
    return 0 if sim_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
