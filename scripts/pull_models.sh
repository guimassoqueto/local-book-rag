#!/usr/bin/env bash
# Download the models named in config/models.yaml into the Ollama volume.
set -euo pipefail

docker compose exec app book-rag pull-models
