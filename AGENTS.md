# Agent Instructions

## Development environment

Preferably work inside the dev container configured in `.devcontainer/`. It
provides a pinned, reproducible environment (Python 3.11 plus `ir_datasets`
installed from the `v2` branch) via the prebuilt image
`ghcr.io/ir-datasets/approval-tests-ir-datasets:0.0.1-dev`. Do not create or
use local Python virtual environments; rely on the dev container instead.

If your tooling supports dev containers, open/build this repository with it
directly. Otherwise, run commands inside the published image, e.g.:

```bash
docker run --rm -it -v "$PWD":/workspaces/approval-tests-ir-datasets \
  -w /workspaces/approval-tests-ir-datasets \
  ghcr.io/ir-datasets/approval-tests-ir-datasets:0.0.1-dev bash
```

## Good engineering practices

- Keep changes small, focused, and consistent with existing code style and
  project conventions.
- Add or update tests for any behavior change; run the test suite
  (`pytest`) before considering work done.
- Prefer clear, self-documenting code; only add comments where intent is not
  obvious.
- Update relevant documentation (README, this file, etc.) when behavior or
  setup instructions change.
- Avoid unrelated changes in the same commit/PR; keep diffs reviewable.
- Do not commit secrets, credentials, or other sensitive data.
- Validate assumptions by running the code/tests rather than guessing.
