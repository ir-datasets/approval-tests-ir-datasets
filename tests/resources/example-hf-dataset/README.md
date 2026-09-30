---
tags:
- ir-datasets
ir_datasets:
  default: eval
  tables:
    docs:
      entity: docs
      file: data/docs.jsonl
    queries:
      entity: queries
      file: data/queries.jsonl
    qrels:
      entity: qrels
      file: data/qrels.jsonl
  benchmarks:
    eval:
      docs: docs
      queries: queries
      qrels: qrels
      metrics:
      - nDCG@10
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
