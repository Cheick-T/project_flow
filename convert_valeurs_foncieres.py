#!/usr/bin/env python3
"""Convert Valeurs foncieres text dump (pipe separated) into CSV for Excel."""

import argparse
import csv
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert pipe-delimited DGFiP data into a CSV readable by Excel."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the original ValeursFoncieres-2024.txt file",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Destination CSV file (will be overwritten if it exists)",
    )
    parser.add_argument(
        "--input-encoding",
        default="cp1252",
        help="Encoding used by the source file (default: cp1252)",
    )
    parser.add_argument(
        "--output-encoding",
        default="utf-8-sig",
        help="Encoding for the CSV file; utf-8-sig adds a BOM for Excel",
    )
    parser.add_argument(
        "--delimiter",
        default=";",
        help="Delimiter for the generated CSV (default: ';' for Excel in FR locales)",
    )
    return parser


def convert_file(src: Path, dest: Path, input_encoding: str, output_encoding: str, delimiter: str) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    with src.open("r", encoding=input_encoding, newline="") as rfp, dest.open(
        "w", encoding=output_encoding, newline=""
    ) as wfp:
        reader = csv.reader(rfp, delimiter="|")
        writer = csv.writer(wfp, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

        for row in reader:
            # Strip trailing carriage returns that may linger on Windows inputs
            cleaned = [field.rstrip("\r") for field in row]
            writer.writerow(cleaned)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    convert_file(args.input, args.output, args.input_encoding, args.output_encoding, args.delimiter)


if __name__ == "__main__":
    main()
