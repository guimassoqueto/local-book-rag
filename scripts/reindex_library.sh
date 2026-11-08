#!/usr/bin/env bash
# Rebuild the index from the original documents with the current configuration. The existing
# library keeps working until the new index is ready.
set -euo pipefail

docker compose exec app book-rag reindex-all "$@"
