import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SUPPORTED_INPUT_FORMATS = {".csv", ".parquet"}


def load_csv(source_path) -> pd.DataFrame:
    """Try common encodings × delimiters until a multi-column parse succeeds."""
    source_path = Path(source_path)
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(source_path, encoding=encoding, sep=sep)
                if len(df.columns) > 1:
                    logging.info(f"Loaded {len(df)} rows from CSV: {source_path}")
                    return df
            except Exception:
                continue
    raise ValueError(
        f"Could not parse '{source_path.name}'. "
        "Make sure it uses comma, semicolon, or tab as separator and is saved as UTF-8 or Latin-1."
    )


def load_parquet(source_path) -> pd.DataFrame:
    source_path = Path(source_path)
    df = pd.read_parquet(source_path, engine="pyarrow")
    logging.info(f"Loaded {len(df)} rows from Parquet: {source_path}")
    return df


def load_data(source_path) -> pd.DataFrame:
    """Load a CSV or Parquet file into a DataFrame. Format is detected by file extension."""
    source_path = Path(source_path)
    ext = source_path.suffix.lower()
    if ext == ".parquet":
        return load_parquet(source_path)
    elif ext == ".csv":
        return load_csv(source_path)
    else:
        raise ValueError(
            f"Unsupported file format '{ext}'. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_INPUT_FORMATS))}"
        )
