#!/usr/bin/env bash
# Safe, GPU-1-only remote job runner for the XORFLOW HPCA suite.
#
# Source of truth stays local.  Remote jobs are serialized through a lock so
# GPU 0 is never touched and independent invocations form a FIFO-like queue.
set -euo pipefail

HOST="${HOST:-mll5090}"
REMOTE_BASE="${REMOTE_BASE:-~/remote-work}"
PROJECT_NAME="${PROJECT_NAME:-HPCA-2-xorflow}"
REMOTE_DIR="${REMOTE_DIR:-${REMOTE_BASE}/${PROJECT_NAME}}"
# Verified on the remote RTX 5090 / driver 575.51.03.  The originally named
# gpu-cu128 environment now contains a CUDA-13 wheel and cannot initialize.
MAMBA_ENV="${MAMBA_ENV:-/home/Rishabh@MLL-5090/envs/gpu-test}"
JOB_DIR="${JOB_DIR:-.xorflow_jobs}"
GPU_ID="${GPU_ID:-1}"

local_commit() { git rev-parse HEAD 2>/dev/null || printf 'uncommitted'; }

sync_up() {
  # This is intentionally a project-specific mirror, not a general remote-work
  # synchronizer.  Results, datasets, checkpoints, and prior artifacts remain
  # remote-only until explicitly pulled with `pull`.
  rsync -az --delete-delay \
    --exclude '.git/' --exclude '__pycache__/' --exclude '.pytest_cache/' \
    --exclude '.venv/' --exclude '.mamba/' --exclude 'data' --exclude 'data/' \
    --exclude 'artifacts*/' --exclude 'results*/' --exclude 'checkpoints/' \
    --exclude 'third_party' --exclude 'third_party/' --exclude '*.zip' --exclude "${JOB_DIR}/" \
    -e ssh ./ "${HOST}:${REMOTE_DIR}/"
}

remote_shell() {
  ssh "${HOST}" "cd ${REMOTE_DIR} && export PATH=\"\$HOME/bin:\$PATH\" && $*"
}

smoke() {
  sync_up
  remote_shell "CUDA_VISIBLE_DEVICES=${GPU_ID} micromamba run -p '${MAMBA_ENV}' python -c 'import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"no-cuda\"); print(torch.cuda.device_count())'"
}

submit() {
  if [[ $# -eq 0 ]]; then echo 'usage: submit <command...>' >&2; exit 2; fi
  sync_up
  local id="$(date -u +%Y%m%dT%H%M%SZ)_$RANDOM"
  local command_b64
  command_b64="$(printf '%s' "$*" | base64 -w0)"
  local commit
  commit="$(local_commit)"
  # The remote runner writes completion state. `flock` serializes every GPU-1
  # job; the base64 command file avoids shell-quoting ambiguity in job payloads.
  remote_shell "mkdir -p '${JOB_DIR}'; job='${JOB_DIR}/${id}'; mkdir -p \"\$job\"; printf '%s' '${command_b64}' | base64 -d > \"\$job/command.sh\"; chmod 700 \"\$job/command.sh\"; printf '%s\\n' '${commit}' > \"\$job/local_commit.txt\"; date -u +%FT%TZ > \"\$job/submitted_utc.txt\"; nohup env XORFLOW_JOB_DIR=\"\$job\" XORFLOW_GPU_ID='${GPU_ID}' XORFLOW_MAMBA_ENV='${MAMBA_ENV}' XORFLOW_QUEUE_LOCK='${JOB_DIR}/gpu${GPU_ID}.lock' bash tools/remote_job_runner.sh > \"\$job/stdout_stderr.log\" 2>&1 & echo \$! > \"\$job/pid\"; printf '%s\\n' '${id}'"
}

list_jobs() {
  remote_shell "if [[ ! -d '${JOB_DIR}' ]]; then exit 0; fi; for d in '${JOB_DIR}'/*; do [[ -d \"\$d\" ]] || continue; id=\$(basename \"\$d\"); status=\$(cat \"\$d/status\" 2>/dev/null || echo queued); pid=\$(cat \"\$d/pid\" 2>/dev/null || echo -); printf '%-28s %-10s %s\\n' \"\$id\" \"\$status\" \"\$pid\"; done | sort"
}

tail_job() {
  [[ $# -eq 1 ]] || { echo 'usage: tail <job-id>' >&2; exit 2; }
  remote_shell "tail -n 80 '${JOB_DIR}/$1/stdout_stderr.log'"
}

pull() {
  rsync -az -e ssh "${HOST}:${REMOTE_DIR}/" ./ \
    --include 'artifacts_hpca_xorflow/***' --include 'results_hpca_xorflow/***' \
    --include '.xorflow_jobs/***' --exclude '*'
}

stage_input() {
  [[ $# -gt 0 ]] || { echo 'usage: stage <relative-path>...' >&2; exit 2; }
  local path parent
  for path in "$@"; do
    [[ -e "$path" && "$path" != /* && "$path" != *".."* ]] || {
      echo "refusing unsafe or missing staged input: $path" >&2; exit 2;
    }
    parent="$(dirname "$path")"
    # The local project historically used a `data` symlink.  A synced dangling
    # symlink is replaced only at this exact staged-input parent, never by a
    # recursive deletion.
    ssh "${HOST}" "if [ -L ${REMOTE_DIR}/${parent} ]; then rm -- ${REMOTE_DIR}/${parent}; fi; mkdir -p ${REMOTE_DIR}/${parent}"
    # Do not use --delete for datasets/traces: staging only ever adds the
    # explicitly named immutable input.
    # Inputs such as `data` and `third_party` are historical repository
    # symlinks.  Stage their real immutable contents, never dangling links.
    rsync -azL -e ssh "$path" "${HOST}:${REMOTE_DIR}/${parent}/"
  done
}

case "${1:-}" in
  sync) sync_up ;;
  smoke) smoke ;;
  submit) shift; submit "$@" ;;
  list) list_jobs ;;
  tail) shift; tail_job "$@" ;;
  pull) pull ;;
  stage) shift; stage_input "$@" ;;
  *)
    echo "usage: $0 {sync|smoke|submit <command...>|list|tail <job-id>|pull|stage <relative-path>...}" >&2
    exit 2
    ;;
esac
