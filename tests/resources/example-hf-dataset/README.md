---
tags:
- ir-datasets
ir_datasets:
  - fragment: null
    type: irds:AdhocBenchmark
    docs: docs
    queries: queries
    qrels: qrels
    metrics:
    - nDCG@10
  - fragment: docs
    type: irds:Docs
    file: data/docs.jsonl
  - fragment: queries
    type: irds:Queries
    file: data/queries.jsonl
  - fragment: qrels
    type: irds:Qrels
    file: data/qrels.jsonl
---

# Example Pangram Dataset

A tiny, self-contained `hf:` (Hugging Face Hub) dataset used by
`tests/test_hf_integration.py`: 10 pangram documents, 3 queries, and one
relevant document per query.

This repository is a real, valid `ir_datasets` HF Hub dataset card -- it is
persisted locally (rather than actually published to the Hub) so the
integration test can exercise the real `ir_datasets.v2.hf_provider` card
parsing and row reading logic against real files, without any network
access.
