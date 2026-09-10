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
