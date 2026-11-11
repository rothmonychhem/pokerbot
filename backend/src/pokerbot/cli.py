"""Command-line entry point (`pokerbot`). Sub-commands arrive in later stories."""

import argparse

from pokerbot import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pokerbot", description="Poker Bot Arena CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
