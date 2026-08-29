# GitHub launch plan

## Repository metadata

Description: **Solver-independent Python toolkit for validating, normalizing, summarizing, and
visualizing crystal-plasticity simulation datasets.**

Suggested topics: `crystal-plasticity`, `materials-science`, `scientific-python`, `data-validation`,
`hdf5`, `simulation-data`, `research-software`, `matplotlib`, `pandas`, `open-science`.

## First issues

1. Add schema authoring and validation helpers for external JSON contracts.
2. Define a documented tensor-valued tabular encoding and component-order examples.
3. Add chunk-aware CPDataKit HDF5 reads and memory benchmarks with synthetic data.
4. Add JSON mapping-file support to the CLI with explicit scientific conventions.
5. Establish an adapter acceptance checklist with official-format and license evidence.
6. Expand property-based tests for malformed nested fields and boundary numeric values.

## Owner actions

Create the GitHub repository, set the description/topics, enable private vulnerability reporting
and branch protection, push only after reviewing `git status`/`git diff --stat`, let CI pass on
every matrix job, create issues, then tag and publish the release using the release notes. PyPI
publication follows package ownership, name availability, two-factor authentication, and trusted
publishing setup.
