#!/usr/bin/env bash
# local-ci deploy job for the corpus-index Worker. Live deploy is disarmed.
# See scripts/deploy/README.md.
exec "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/run-job.sh" --job corpus-index "$@"
