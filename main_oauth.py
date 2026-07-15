"""Download the MEAD dataset from Google Drive.

Authentication is handled using Google's OAuth desktop application flow.
Run create_oauth_token.py first (on a machine with a browser) to generate
token.json; this script only consumes an existing token.json and refreshes
it automatically as it expires, so it can run unattended for as long as the
download takes, on a local machine, a headless machine, or in a SLURM job.

Downloads are written to .part files and use HTTP byte ranges so interrupted
downloads can be resumed.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from tqdm import tqdm


# Read-only access to files in Google Drive.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Each HTTP request downloads at most 64 MiB. This means credentials can be
# refreshed between chunks rather than relying on one multi-hour connection.
REMOTE_CHUNK_SIZE = 64 * 1024 * 1024

# requests.iter_content() writes smaller pieces to disk without holding an
# entire 64 MiB remote chunk in memory.
WRITE_CHUNK_SIZE = 1024 * 1024

MAX_RETRIES = 8


def load_credentials(main_dir: Path) -> Credentials:
    token_file = main_dir / "token.json"

    if not token_file.exists():
        raise FileNotFoundError(
            f"No OAuth token found at {token_file}.\n"
            "Run create_oauth_token.py on a machine with a browser, "
            "then copy token.json (and credentials.json) to this node."
        )

    creds = Credentials.from_authorized_user_file(
        str(token_file),
        SCOPES,
    )

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            print("Refreshing Google OAuth access token...")
            creds.refresh(Request())
            token_file.write_text(creds.to_json(), encoding="utf-8")
            os.chmod(token_file, 0o600)
        else:
            raise RuntimeError(
                "The saved Google OAuth credentials cannot be refreshed.\n"
                "Generate a new token.json on a machine with a browser "
                "and copy it to this node."
            )

    return creds

def ensure_valid_credentials(
    creds: Credentials,
    token_file: Path,
    *,
    force_refresh: bool = False,
) -> None:
    """Refresh credentials if necessary and persist the refreshed token."""

    if force_refresh or not creds.valid:
        if not creds.refresh_token:
            raise RuntimeError(
                "The stored OAuth credentials do not contain a refresh token. "
                "Delete token.json and authorize the application again."
            )

        creds.refresh(Request())
        token_file.write_text(creds.to_json(), encoding="utf-8")

        try:
            os.chmod(token_file, 0o600)
        except OSError:
            pass


def download_file(
    creds: Credentials,
    token_file: Path,
    file_id: str,
    dest_filename: Path,
) -> None:
    """Download a Drive file, resuming from an existing .part file."""

    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

    part_filename = dest_filename.with_name(dest_filename.name + ".part")
    downloaded = part_filename.stat().st_size if part_filename.exists() else 0

    if downloaded:
        print(
            f"Resuming {dest_filename.name} from "
            f"{downloaded / (1024**2):.1f} MiB"
        )

    while True:
        range_end = downloaded + REMOTE_CHUNK_SIZE - 1

        for attempt in range(1, MAX_RETRIES + 1):
            ensure_valid_credentials(creds, token_file)

            headers = {
                "Authorization": f"Bearer {creds.token}",
                "Range": f"bytes={downloaded}-{range_end}",
            }

            try:
                response = requests.get(
                    url,
                    headers=headers,
                    stream=True,
                    timeout=(30, 300),
                )

                # A token can theoretically become invalid between our local
                # validity check and the request reaching Google.
                if response.status_code == 401:
                    response.close()
                    ensure_valid_credentials(
                        creds,
                        token_file,
                        force_refresh=True,
                    )
                    continue

                # 416 means the local .part file is already at the end.
                if response.status_code == 416 and downloaded > 0:
                    part_filename.replace(dest_filename)
                    print(f"Download complete: {dest_filename}")
                    return

                if response.status_code not in {200, 206}:
                    error_text = response.text[:1000]
                    response.close()

                    if response.status_code in {429, 500, 502, 503, 504}:
                        delay = min(2**attempt, 60)
                        print(
                            f"HTTP {response.status_code}; "
                            f"retrying after {delay}s..."
                        )
                        time.sleep(delay)
                        continue

                    raise RuntimeError(
                        f"Google Drive returned HTTP "
                        f"{response.status_code} for file_id={file_id}:\n"
                        f"{error_text}"
                    )

                # A resumed request must return 206 Partial Content. If it
                # returns 200, Google ignored the Range header and appending
                # would corrupt the file.
                if downloaded > 0 and response.status_code != 206:
                    response.close()
                    raise RuntimeError(
                        "Google Drive ignored the Range header while resuming. "
                        f"Remove {part_filename} and retry."
                    )

                bytes_written = 0

                with part_filename.open("ab") as output:
                    for chunk in response.iter_content(
                        chunk_size=WRITE_CHUNK_SIZE
                    ):
                        if chunk:
                            output.write(chunk)
                            bytes_written += len(chunk)

                    output.flush()
                    os.fsync(output.fileno())

                content_range = response.headers.get("Content-Range")
                response.close()

                downloaded += bytes_written

                if bytes_written == 0:
                    raise RuntimeError(
                        f"No data received for Drive file {file_id}."
                    )

                # A partial response normally looks like:
                # Content-Range: bytes 0-67108863/123456789
                total_size: int | None = None

                if content_range and "/" in content_range:
                    total_text = content_range.rsplit("/", 1)[1]

                    if total_text != "*":
                        total_size = int(total_text)

                if total_size is not None:
                    print(
                        f"\r{dest_filename.name}: "
                        f"{downloaded / (1024**2):.1f} / "
                        f"{total_size / (1024**2):.1f} MiB",
                        end="",
                        flush=True,
                    )

                    if downloaded >= total_size:
                        print()
                        part_filename.replace(dest_filename)
                        print(f"Download complete: {dest_filename}")
                        return

                # If fewer bytes than requested arrived, this was the final
                # chunk even when no Content-Range total was supplied.
                if bytes_written < REMOTE_CHUNK_SIZE:
                    part_filename.replace(dest_filename)
                    print(f"\nDownload complete: {dest_filename}")
                    return

                # Successfully downloaded this remote chunk.
                break

            except (
                requests.ConnectionError,
                requests.Timeout,
            ) as exc:
                if attempt == MAX_RETRIES:
                    raise RuntimeError(
                        f"Download repeatedly failed for {file_id}."
                    ) from exc

                delay = min(2**attempt, 60)
                print(
                    f"\nConnection interrupted: {exc}. "
                    f"Retrying after {delay}s..."
                )
                time.sleep(delay)

        else:
            raise RuntimeError(
                f"Exceeded retry limit for Drive file {file_id}."
            )


def main() -> None:
    main_dir = Path(__file__).parent.resolve()
    token_file = main_dir / "token.json"

    creds = load_credentials(main_dir)

    file_df = pd.read_csv(main_dir / "mead_file_list.csv")
    mead_dir = main_dir / "MEAD"

    for _, row in tqdm(
        file_df.iterrows(),
        total=file_df.shape[0],
        unit="file",
    ):
        this_folder = mead_dir / str(row["person_folder"])
        this_file = this_folder / str(row["tar_file"])

        if this_file.exists():
            tqdm.write(f"{this_file} is already here")
            continue

        this_folder.mkdir(exist_ok=True, parents=True)

        tqdm.write(f"{this_file} to be downloaded")

        download_file(
            creds=creds,
            token_file=token_file,
            file_id=str(row["id_code"]),
            dest_filename=this_file,
        )


if __name__ == "__main__":
    main()
