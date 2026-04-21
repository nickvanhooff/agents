import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SUPPORTED_FORMATS = {"parquet", "jsonl"}


def to_parquet(df: pd.DataFrame, output_path: Path) -> Path:
    """Write df to Parquet. Returns the output path."""
    output_path = Path(output_path)
    df.to_parquet(output_path, index=False, engine="pyarrow")
    logging.info(f"Exported {len(df)} rows to Parquet: {output_path}")
    return output_path


def to_jsonl(df: pd.DataFrame, output_path: Path) -> Path:
    """Write df to JSON Lines (one JSON object per row). Returns the output path."""
    output_path = Path(output_path)
    df.to_json(output_path, orient="records", lines=True, force_ascii=False)
    logging.info(f"Exported {len(df)} rows to JSONL: {output_path}")
    return output_path


def convert_csv(csv_path: Path, fmt: str) -> Path:
    """
    Read an existing CSV and convert it to the requested format.
    fmt must be 'parquet' or 'jsonl'.
    Returns the path of the converted file.
    """
    fmt = fmt.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format '{fmt}'. Choose from: {SUPPORTED_FORMATS}")

    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)

    stem = csv_path.stem
    output_path = csv_path.parent / f"{stem}.{fmt}"

    if fmt == "parquet":
        return to_parquet(df, output_path)
    else:
        return to_jsonl(df, output_path)
