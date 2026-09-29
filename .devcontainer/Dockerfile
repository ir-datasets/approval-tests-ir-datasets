# docker build -t ghcr.io/ir-datasets/approval-tests-ir-datasets:0.0.1-dev .
FROM python:3.11-slim

# System dependencies required to fetch and build ir-datasets and its dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

# Install ir-datasets from the v2 branch.
RUN pip install --no-cache-dir "git+https://github.com/ir-datasets/ir-datasets.git@v2"

# Install test dependencies (kept in sync with pyproject.toml's [project.optional-dependencies].test).
RUN pip install --no-cache-dir "coverage[toml]>=7.6" "pytest>=8.3"

WORKDIR /workspaces/approval-tests-ir-datasets
