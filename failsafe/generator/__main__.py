from .cli import app

def main() -> None:
    app()        # run Typer directly — no get_command()

if __name__ == "__main__":
    main()
