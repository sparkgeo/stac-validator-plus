To install all dependencies:
`uv sync --all-extras`

To just install the CLI:
`uv sync --extra cli`

To just install the API:
`uv sync --extra api`

For dev dependencies, append `--group dev` to the above commands.
Also run `pre-commit install` to install the pre-commit hooks for Ruff linting and formatting.

To run the CLI: `uv run python -m stac_validator_plus`

To run the API: `uv run uvicorn stac_validator_plus.api:app`

To build:
`uv build --no-sources`
