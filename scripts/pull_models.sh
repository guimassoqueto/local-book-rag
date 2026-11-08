#!/usr/bin/env bash
# Download the models named in config/models.yaml. --all adds every candidate with a profile,
# which the benchmarks compare.
set -euo pipefail

docker compose exec app book-rag pull-models "$@"
