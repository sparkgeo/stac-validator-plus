def _load_click():
    try:
        import rich_click as click
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "The CLI is installed, but its optional dependencies are missing.\n"
            "Install the CLI extra, for example:\n"
            "  uv sync --extra cli\n"
            "or:\n"
            "  uv pip install '.[cli]'"
        ) from exc
    return click


def main() -> None:
    click = _load_click()

    @click.command()
    def app() -> None:
        click.echo("Hello from stac-validator-plus")

    app()


if __name__ == "__main__":
    main()
