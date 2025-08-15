"""Download MEAD using curl

This script downloads the MEAD dataset from Google Drive using pycurl.
This has no arguments BUT it does expect the GOOGLE_API_TOKEN environment variable
to be set.
The MEAD dataset is downloaded into the "MEAD" subdirectory.
If files have already been downloaded, they will not be downloaded again.

This relies on the `mead_file_list.csv` being up to date, which it may no longer be.
"""

import os
from pathlib import Path

import pandas as pd
import pycurl
from tqdm import tqdm


def download_file(access_token, file_id, dest_filename):
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

    header_buf = bytearray()

    def header_collector(data):
        header_buf.extend(data)
        return len(data)

    with open(dest_filename, "wb") as f:
        c = pycurl.Curl()
        c.setopt(pycurl.URL, url.encode())
        c.setopt(
            pycurl.HTTPHEADER,
            [
                f"Authorization: Bearer {access_token}",
            ],
        )
        c.setopt(pycurl.HEADERFUNCTION, header_collector)
        c.setopt(pycurl.WRITEDATA, f)
        c.setopt(pycurl.FAILONERROR, False)
        c.perform()
        status = c.getinfo(pycurl.RESPONSE_CODE)
        c.close()

        if status != 200:
            os.remove(dest_filename)
            raise RuntimeError(
                f"Google Drive returned HTTP {status} for file_id={file_id}.\n"
                "Access token may be expired or you may have hit a quota limit."
            )
        else:
            print("Download Complete")


def main():
    main_dir = Path(__file__).parent.resolve()

    GOOGLE_API_TOKEN = os.getenv("GOOGLE_API_TOKEN")

    if not GOOGLE_API_TOKEN:
        raise ValueError("Please set the GOOGLE_API_TOKEN environment variable.")

    file_df = pd.read_csv(main_dir / "mead_file_list.csv")
    mead_dir = main_dir / "MEAD"
    for _, row in tqdm(file_df.iterrows(), total=file_df.shape[0]):
        this_folder = mead_dir / row["person_folder"]
        this_file = this_folder / row["tar_file"]
        if this_file.exists():
            print(f"{this_file} is already here")
            continue

        this_folder.mkdir(exist_ok=True, parents=True)
        print(f"{this_file} to be downloaded.")
        download_file(GOOGLE_API_TOKEN, str(row["id_code"]), str(this_file))


if __name__ == "__main__":
    main()
