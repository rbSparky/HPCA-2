#!/usr/bin/env bash
# Reproducible CACTI 7 launcher. The user-level ~/.local/bin/cacti wrapper
# points to the same logic; this copy is retained in the project handoff.
set -euo pipefail
image="${CACTI_IMAGE:-local/cacti-hp:7.0}"
if [[ $# -eq 0 ]]; then
  exec docker run --rm --network none "$image"
elif [[ $# -eq 1 && "$1" != -* ]]; then
  cfg="$(realpath -e -- "$1")"
  exec docker run --rm --network none --mount "type=bind,src=$cfg,dst=/input/cache.cfg,readonly" "$image" -infile /input/cache.cfg
elif [[ $# -eq 2 && "$1" == "-infile" ]]; then
  cfg="$(realpath -e -- "$2")"
  exec docker run --rm --network none --mount "type=bind,src=$cfg,dst=/input/cache.cfg,readonly" "$image" -infile /input/cache.cfg
else
  exec docker run --rm --network none "$image" "$@"
fi
