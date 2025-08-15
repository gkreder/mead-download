"""Extract MEAD tar files

This script extracts tar files from the MEAD dataset into a specified
destination directory.
The destination directory must exist before running the script and is the
only required argument.
It assumes that the MEAD dataset was downloaded and extracted to the
"MEAD" subdirectory, which is what the other two scripts do by default.
"""

import argparse
import tarfile
from pathlib import Path

import pandas as pd
from tqdm import tqdm


def main(destination: str):
    main_dir = Path(__file__).parent.resolve()
    destination = Path(destination).resolve()
    if not destination.exists():
        msg = f"Destination directory {destination} does not exist."
        raise FileNotFoundError(msg)
    file_df = pd.read_csv(main_dir / "mead_file_list.csv")
    mead_dir = main_dir / "MEAD"
    for _, row in tqdm(file_df.iterrows(), total=file_df.shape[0]):
        this_folder = mead_dir / row["person_folder"]
        this_file = this_folder / row["tar_file"]
        destination_folder = destination / row["person_folder"]
        destination_folder.mkdir(parents=True, exist_ok=True)

        if not this_file.exists():
            msg = f"{this_file} is missing"
            raise FileNotFoundError(msg)

        # Extract the tar file to the destination
        with tarfile.open(this_file, "r") as tar:
            tar.extractall(path=str(destination_folder))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process MEAD files.")
    parser.add_argument(
        "destination",
        type=str,
        help="Destination directory for MEAD files.",
    )
    args = parser.parse_args()
    main(args.destination)
