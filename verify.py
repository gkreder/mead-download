"""Verify downloaded MEAD files against Google Drive metadata.

For every entry in mead_file_list.csv, this script:

1. Checks that the local file exists.
2. Retrieves the expected size and MD5 checksum from Google Drive.
3. Checks the local file size.
4. Calculates the local MD5 checksum.
5. Writes a detailed report to mead_verification.csv.

This script does not download file contents from Google Drive.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from tqdm import tqdm


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Larger blocks generally improve sequential hashing throughput.
HASH_CHUNK_SIZE = 16 * 1024 * 1024


def load_credentials(main_dir: Path) -> Credentials:
    """Load OAuth credentials and refresh them when required."""

    token_file = main_dir / "token.json"

    if not token_file.exists():
        raise FileNotFoundError(
            f"OAuth token not found: {token_file}"
        )

    credentials = Credentials.from_authorized_user_file(
        str(token_file),
        SCOPES,
    )

    if not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            print("Refreshing Google OAuth access token...")
            credentials.refresh(Request())
            token_file.write_text(
                credentials.to_json(),
                encoding="utf-8",
            )

            try:
                os.chmod(token_file, 0o600)
            except OSError:
                pass
        else:
            raise RuntimeError(
                "The saved OAuth credentials cannot be refreshed. "
                "Generate a new token.json."
            )

    return credentials


def ensure_valid_credentials(
    credentials: Credentials,
    token_file: Path,
    *,
    force_refresh: bool = False,
) -> None:
    """Ensure that the current access token is valid."""

    if force_refresh or not credentials.valid:
        if not credentials.refresh_token:
            raise RuntimeError(
                "OAuth credentials do not contain a refresh token."
            )

        credentials.refresh(Request())
        token_file.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )


def get_drive_metadata(
    session: requests.Session,
    credentials: Credentials,
    token_file: Path,
    file_id: str,
) -> dict[str, Any]:
    """Retrieve filename, size and MD5 metadata for one Drive file."""

    url = (
        "https://www.googleapis.com/drive/v3/files/"
        f"{file_id}"
    )

    params = {
        "fields": "id,name,size,md5Checksum,mimeType",
        "supportsAllDrives": "true",
    }

    for attempt in range(2):
        ensure_valid_credentials(credentials, token_file)

        response = session.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {credentials.token}",
            },
            timeout=60,
        )

        if response.status_code == 401 and attempt == 0:
            ensure_valid_credentials(
                credentials,
                token_file,
                force_refresh=True,
            )
            continue

        if response.status_code != 200:
            raise RuntimeError(
                f"Drive returned HTTP {response.status_code} "
                f"for file ID {file_id}: {response.text[:500]}"
            )

        return response.json()

    raise RuntimeError(
        f"Could not authenticate Drive request for {file_id}"
    )


def calculate_md5(
    filename: Path,
    progress: tqdm | None = None,
) -> str:
    """Calculate a file's MD5 checksum without loading it into memory."""

    digest = hashlib.md5()

    with filename.open("rb") as file:
        while chunk := file.read(HASH_CHUNK_SIZE):
            digest.update(chunk)

            if progress is not None:
                progress.update(len(chunk))

    return digest.hexdigest()


def verify_file(
    local_file: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Compare one local file against its Drive metadata."""

    expected_name = metadata.get("name")
    expected_md5 = metadata.get("md5Checksum")
    expected_size_raw = metadata.get("size")
    expected_size = (
        int(expected_size_raw)
        if expected_size_raw is not None
        else None
    )

    result: dict[str, Any] = {
        "local_path": str(local_file),
        "drive_name": expected_name,
        "expected_size": expected_size,
        "local_size": None,
        "expected_md5": expected_md5,
        "local_md5": None,
        "size_match": False,
        "md5_match": False,
        "status": None,
        "error": None,
    }

    if not local_file.exists():
        result["status"] = "MISSING"
        return result

    if not local_file.is_file():
        result["status"] = "NOT_A_FILE"
        return result

    local_size = local_file.stat().st_size
    result["local_size"] = local_size

    if expected_size is not None:
        result["size_match"] = local_size == expected_size

        # A size mismatch is already conclusive. Avoid spending time hashing
        # a file that definitely cannot match the Drive object.
        if not result["size_match"]:
            result["status"] = "SIZE_MISMATCH"
            return result

    if expected_md5 is None:
        result["status"] = "NO_REMOTE_MD5"
        return result

    with tqdm(
        total=local_size,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        desc=local_file.name,
        leave=False,
    ) as progress:
        local_md5 = calculate_md5(local_file, progress)

    result["local_md5"] = local_md5
    result["md5_match"] = local_md5.lower() == expected_md5.lower()

    if result["md5_match"]:
        result["status"] = "OK"
    else:
        result["status"] = "MD5_MISMATCH"

    return result


def main() -> int:
    main_dir = Path(__file__).parent.resolve()
    csv_file = main_dir / "mead_file_list.csv"
    token_file = main_dir / "token.json"
    mead_dir = main_dir / "MEAD"
    report_file = main_dir / "mead_verification.csv"

    credentials = load_credentials(main_dir)
    file_df = pd.read_csv(csv_file)

    required_columns = {
        "person_folder",
        "tar_file",
        "id_code",
    }

    missing_columns = required_columns - set(file_df.columns)

    if missing_columns:
        raise ValueError(
            "CSV is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    results: list[dict[str, Any]] = []

    with requests.Session() as session:
        rows = file_df.iterrows()

        for _, row in tqdm(
            rows,
            total=len(file_df),
            unit="file",
            desc="Verifying",
        ):
            local_file = (
                mead_dir
                / str(row["person_folder"])
                / str(row["tar_file"])
            )
            file_id = str(row["id_code"])

            base_result = {
                "file_id": file_id,
                "person_folder": str(row["person_folder"]),
                "tar_file": str(row["tar_file"]),
            }

            try:
                metadata = get_drive_metadata(
                    session=session,
                    credentials=credentials,
                    token_file=token_file,
                    file_id=file_id,
                )

                verification = verify_file(
                    local_file=local_file,
                    metadata=metadata,
                )

                result = {
                    **base_result,
                    **verification,
                }

            except Exception as error:
                result = {
                    **base_result,
                    "local_path": str(local_file),
                    "drive_name": None,
                    "expected_size": None,
                    "local_size": (
                        local_file.stat().st_size
                        if local_file.exists()
                        else None
                    ),
                    "expected_md5": None,
                    "local_md5": None,
                    "size_match": False,
                    "md5_match": False,
                    "status": "ERROR",
                    "error": str(error),
                }

            results.append(result)

            # Continuously update the report so progress is preserved if the
            # job or interactive session is interrupted.
            pd.DataFrame(results).to_csv(
                report_file,
                index=False,
            )

    result_df = pd.DataFrame(results)

    print()
    print("Verification summary")
    print("--------------------")

    counts = result_df["status"].value_counts()

    for status, count in counts.items():
        print(f"{status:16} {count}")

    print(f"\nFull report: {report_file}")

    failed = result_df[result_df["status"] != "OK"]

    if not failed.empty:
        print("\nFiles requiring attention:")

        for _, row in failed.iterrows():
            print(f"  [{row['status']}] {row['local_path']}")

            if pd.notna(row.get("error")):
                print(f"      {row['error']}")

        return 1

    print("\nAll downloaded files match Google Drive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
