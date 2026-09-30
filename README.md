# approval-tests-ir-datasets
A utility inspired by approval tests to easily add unit and integration tests for ir-datasets.

## Installation

```bash
pip install .
```

## Usage

```python
from approval_tests_ir_datasets import DatasetNotFoundError, verify

try:
    verify("dataset-id")
except DatasetNotFoundError as exc:
    print(exc)
```

At the moment, `verify` raises `DatasetNotFoundError` for every input because
dataset lookup support has not been implemented yet.

## TODOs

- `approval_tests_ir_datasets.hf_local.local_hf_repo` (and `verify`'s
  `hf_local_dir` parameter), plus the `hf-local:` provider
  (`approval_tests_ir_datasets.hf_local_provider`, which lets a local
  directory be loaded/verified directly by path, e.g.
  `verify("hf-local:tests/resources/example-hf-dataset/docs")`), both let an
  `hf:`-shaped dataset be resolved against a local directory instead of the
  real Hugging Face Hub, but only by monkeypatching `ir_datasets.v2.hf_provider`'s
  private, network-touching internals (`_hf_lib`, plus its process-wide
  caches) -- there is no first-class, supported "local hf: repo" feature in
  `ir_datasets` itself yet. Once `ir_datasets` gains a real, documented way
  to do this (e.g. a dedicated test hook, or a `file://`-style repo id),
  `hf_local.py` and `hf_local_provider.py` should be rewritten (or removed
  entirely) to use that instead.
