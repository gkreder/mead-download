"""Download MEAD using gdown

This script downloads the MEAD dataset using the gdown library.
This can work well but does hit some problems with api limits, which is why the other
script might be better.

This relies on the `mead_file_list.csv` being up to date, which it may no longer be.

"""

from pathlib import Path

import gdown
import pandas as pd
from tqdm import tqdm


def main():
    main_dir = Path(__file__).parent.resolve()

    file_df = pd.read_csv(main_dir / "mead_file_list.csv")
    mead_dir = main_dir / "MEAD"
    for _, row in tqdm(file_df.iterrows(), total=file_df.shape[0]):
        this_folder = mead_dir / row["person_folder"]
        this_file = this_folder / row["tar_file"]
        if this_file.exists():
            print(f"{this_file} is already here")
            continue

        this_folder.mkdir(exist_ok=True, parents=True)
        try:
            gdown.download(id=row["id_code"], output=str(this_file))
        except Exception as error:
            print(f"{this_file} gives error")
            print(error)


if __name__ == "__main__":
    main()
