"""Generate token.json for the MEAD OAuth downloader.

Run this once, on a machine with a browser, to authorize access to Google
Drive. It writes token.json alongside this script; copy both credentials.json
and token.json to wherever main_oauth.py will actually run the download
(the same machine, or a separate local/headless/SLURM machine).
"""

from __future__ import annotations

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def main() -> None:
    main_dir = Path(__file__).parent.resolve()
    credentials_file = main_dir / "credentials.json"
    token_file = main_dir / "token.json"

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_file),
        SCOPES,
    )
    creds = flow.run_local_server(port=0)

    token_file.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(token_file, 0o600)

    print(f"Created {token_file}")


if __name__ == "__main__":
    main()
