import pandas as pd
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_data(source_path: str) -> pd.DataFrame:
    """
    Loads data from a given source.
    Currently implements CSV loading, but is designed to be swapped out
    for other connectors (e.g., Power BI) in the future.
    """
    logging.info(f"Attempting to load data from: {source_path}")
    
    try:
        # Load the CSV file into a Pandas DataFrame
        df = pd.read_csv(source_path)
        logging.info(f"Successfully loaded {len(df)} rows from {source_path}")
        return df
    except FileNotFoundError:
        logging.error(f"Error: The file '{source_path}' was not found.")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading data: {e}")
        raise
