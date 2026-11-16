#!/usr/bin/env bash
# Print the runtime requirements pinned by uv.lock, minus the torch stack (torch, torchvision,
# torchcodec, triton and the CUDA wheels), which every image variant installs from its own index.
# Usage (inside the image build, from the repository root): docker/requirements-from-lock.sh > req.txt
set -euo pipefail
uv export --frozen --no-dev --no-emit-project --no-hashes --no-header --no-annotate \
  --format requirements-txt \
  | grep -vE '^(torch|torchvision|torchcodec|triton|nvidia-[a-z0-9-]+|cuda-[a-z0-9-]+)(==| @)'
