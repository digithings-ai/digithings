#!/usr/bin/env bash
# local-ci deploy job for the stack Worker. Live deploy is disarmed.
# See scripts/deploy/README.md.
exec "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/run-job.sh" --job stack "$@"
