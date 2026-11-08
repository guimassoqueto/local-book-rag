#!/usr/bin/env bash
# Reset the library from inside the application, which asks for confirmation.
#
#   scripts/reset_library.sh               delete what is derived, keeping the original documents
#   scripts/reset_library.sh --everything  delete the whole library, originals included
#
# Neither touches the Docker volumes or the models in Ollama. `docker compose down -v` would.
set -euo pipefail

if [ "${1:-}" = "--everything" ]; then
    docker compose exec app book-rag reset-everything
else
    docker compose exec app book-rag reset-index
fi
