# approval-tests-ir-datasets
A utility inspired by approval tests to easily add unit and integration tests for ir-datasets.

## Installation

```bash
pip install .
```

## Usage

```python
from approval_tests_ir_datasets import verify

verify("dataset-id")  # raises ValueError: Dataset 'dataset-id' does not exist.
```
