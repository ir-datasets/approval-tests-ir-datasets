# docker build -t ghcr.io/ir-datasets/approval-tests-ir-datasets:0.0.1-dev .
FROM python:3.11-slim

# System dependencies required to fetch and build ir-datasets and its dependencies,
# plus the Docker CLI (used to run TIRA software via "tira-cli run local", talking
# to the Docker daemon via the socket mounted into this container -- see
# .devcontainer/devcontainer.json).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    docker.io \
    docker-cli \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

# Install ir-datasets from the v2 branch.
RUN pip install --no-cache-dir "git+https://github.com/ir-datasets/ir-datasets.git@v2"

# Install test dependencies (kept in sync with pyproject.toml's [project.optional-dependencies].test).
RUN pip install --no-cache-dir "coverage[toml]>=7.6" "pytest>=8.3"

# Install the TIRA client, used by PyTerrierIndexVerifier to run TIRA software
# (e.g. "ir-benchmarks/tira-ir-starter/Index (tira-ir-starter-pyterrier)") locally.
RUN pip install --no-cache-dir "tira"

# Install Jupyter, so notebooks (e.g. tutorial/example.ipynb) can be run directly
# in the dev container.
RUN pip install --no-cache-dir "jupyter" "ipykernel"

# Install ir_measures, used by EvaluationVerifier to compute nDCG@10, recip_rank
# and Recall@100 for RetrievalVerifier's cached runs against a dataset's qrels.
RUN pip install --no-cache-dir "ir_measures"

WORKDIR /workspaces/approval-tests-ir-datasets
