#!/usr/bin/env bash
# Safe hourly health monitor for the remote reviewer-spec campaign.
# It is intentionally read-only: anomalies are recorded for agent review, not
# acted on by an unattended shell process.
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_dir="$project_root/results_hpca_xorflow/reviewer_spec_v3/monitor"
mkdir -p "$log_dir"
interval_seconds="${1:-3600}"
[[ "$interval_seconds" =~ ^[0-9]+$ ]] && (( interval_seconds > 0 )) || { echo 'interval must be a positive integer' >&2; exit 2; }

while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  snapshot="$log_dir/health_${stamp}.md"
  {
    printf '# Reviewer-spec queue health — %s UTC\n\n' "$(date -u +%FT%TZ)"
    printf '## Queue\n\n```text\n'
    "$project_root/tools/remote_xorflow.sh" list
    printf '```\n\n## Active workload processes\n\n```text\n'
    ssh mll5090 "ps -eo pid,etime,pcpu,pmem,cmd --sort=-pcpu | grep -E 'xorflow\\.(ablation|physical_traffic|decoder_sim|system_schedule)|run_spec_lane' | grep -v grep || true"
    printf '```\n\n## Remote storage\n\n```text\n'
    ssh mll5090 "df -h ~ | tail -n 1; du -sh ~/remote-work/HPCA-2-xorflow/results_hpca_xorflow/reviewer_spec_v3 2>/dev/null || true"
    printf '```\n'
  } > "$snapshot"
  ln -sfn "$(basename "$snapshot")" "$log_dir/latest.md"
  # This is deliberately printed to the attached terminal.  The coding agent
  # receives it as a wake-up event and can inspect/repair the campaign instead
  # of relying on an unattended background process.
  printf 'HEALTH_SNAPSHOT=%s\nNEXT_CHECK_SECONDS=%s\n' "$snapshot" "$interval_seconds"
  sleep "$interval_seconds"
done
