import rich_click as click


def main() -> None:
    @click.command()
    def app() -> None:
        click.echo("Hello from stac-validator-plus")

    app()


if __name__ == "__main__":
    main()
