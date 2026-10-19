import argparse
import sys
from pathlib import Path

from alpha import VERSION

PLUGIN_ROOT: Path = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alpha")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="print the alpha version")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(VERSION)
        return 0
    return 2  # unreachable: argparse rejects unknown commands


if __name__ == "__main__":
    sys.exit(main())
