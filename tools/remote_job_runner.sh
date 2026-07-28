#!/usr/bin/env bash
# Executed on the remote host by remote_xorflow.sh.  Keeping the runner in the
# repository makes completion status and GPU pinning auditable.
set -euo pipefail

: "${XORFLOW_JOB_DIR:?XORFLOW_JOB_DIR must name this job directory}"
: "${XORFLOW_GPU_ID:=1}"
: "${XORFLOW_MAMBA_ENV:?XORFLOW_MAMBA_ENV must name a micromamba prefix}"
: "${XORFLOW_QUEUE_LOCK:?XORFLOW_QUEUE_LOCK must name the GPU lock}"

exec 9>"${XORFLOW_QUEUE_LOCK}"
flock 9
date -u +%FT%TZ > "${XORFLOW_JOB_DIR}/started_utc.txt"
printf running > "${XORFLOW_JOB_DIR}/status"
export CUDA_VISIBLE_DEVICES="${XORFLOW_GPU_ID}"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

if micromamba run -p "${XORFLOW_MAMBA_ENV}" bash "${XORFLOW_JOB_DIR}/command.sh"; then
  printf succeeded > "${XORFLOW_JOB_DIR}/status"
  date -u +%FT%TZ > "${XORFLOW_JOB_DIR}/finished_utc.txt"
else
  status=$?
  printf failed > "${XORFLOW_JOB_DIR}/status"
  printf '%s' "${status}" > "${XORFLOW_JOB_DIR}/exit_code"
  date -u +%FT%TZ > "${XORFLOW_JOB_DIR}/finished_utc.txt"
  exit "${status}"
fi
