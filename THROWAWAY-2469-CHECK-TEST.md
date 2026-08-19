# Throwaway PR — verifying #2469's three checks post correctly

This file exists only to open a test PR against `develop` that touches no
component path (`digibase/`, `digikey/`, `digiquant/`, etc.). Goal: confirm
`Required checks passed`, `doc-links + agents-init`, and
`mypy — digibase + digikey` all post a real conclusion on a PR shape like
this — the exact worst case `fd6de617f` was written to make safe — before
#2469 makes any of them a required status check on `develop`.

This PR will be closed without merging once the checks are confirmed. Do
not merge it.
