# MEAD Download

This repository contains scripts to download the MEAD dataset from Google Drive.
The [MEAD Website is here.](https://wywu.github.io/projects/MEAD/MEAD.html)

Downloading lots of files from google drive can be a hassle, so these scripts aim to make it easier.

To do so you can either use `gdown` or `pycurl` for downloading files.
Which one will depend if you hit the API limits.

For the `pycurl` script you will need to set the `GOOGLE_API_TOKEN` environment
variable.
This [StackOverflow Post](https://stackoverflow.com/a/67550427) was useful in
understanding how to set this up.

The steps are:

* Go to <https://developers.google.com/oauthplayground/>
* Select the Scope `https://www.googleapis.com/auth/drive.readonly`
* Click Authorize APIs and then Exchange authorization code for tokens
* Copy the `Access token` and set it to the environment variable `GOOGLE_API_TOKEN`

## Usage

To use the downloader, you can set it up by using the following commands.

```bash
git clone https://github.com/alexeatscake/mead-download
cd mead-download
python -m venv .venv
source .venv/bin/activate
pip install .
```

To use the downloader, you can run the following command:

```bash
export GOOGLE_API_TOKEN="YOUR_GOOGLE_API_TOKEN"
python main_curl.py
```

This will start the download process for the MEAD dataset.

## Things to Note

* The MEAD dataset is quite large (400 GB), so make sure you have enough disk space before starting the download.
* The `pycurl` package may have additional system dependencies; the code did function properly in a Linux environment with the necessary libraries installed.
* The google drive URLs might not be stable, so the `mead_file_list.csv` may need to be updated periodically.

## OAuth Downloader (recommended for large downloads)

The `GOOGLE_API_TOKEN` approach above (via the OAuth Playground) only produces
an access token that expires after an hour, so downloading the full 400 GB
dataset means manually refreshing it over and over. `main_oauth.py` instead
uses Google's OAuth desktop application flow, which stores a refresh token
and automatically refreshes the access token as needed, so a download can run
unattended for as long as it takes.

### 1. Create OAuth credentials

* Go to the [Google Cloud Console](https://console.cloud.google.com/) and
  create (or select) a project.
* Enable the **Google Drive API** for that project.
* Under **APIs & Services > Credentials**, create an **OAuth client ID** of
  type **Desktop app**.
* Download the resulting JSON file and save it as `credentials.json` in the
  repository root.

`credentials.json` identifies the application; it is not itself
authorization to access anyone's Drive.

### 2. Generate an access token

This step always requires a browser, so it must be run on a local machine
(not a headless node or SLURM job):

```bash
python create_oauth_token.py
```

This opens a browser window to authorize access, then writes `token.json`
next to `credentials.json`. Do this once; `main_oauth.py` automatically
refreshes the token as it expires from then on.

### 3. Run the download

With `credentials.json` and `token.json` in place, run:

```bash
python main_oauth.py
```

If you have the disk space and time, this can simply be run on the same
local machine right after step 2. Alternatively, once `token.json` exists,
you can copy both `credentials.json` and `token.json` to a different
machine — a headless server, or a cluster — and run `main_oauth.py` there
instead; the token generation step (2) never needs to be repeated, only the
download step needs to run wherever you actually want the data to land.

#### Running as a SLURM job

To run the download as a SLURM job, first copy `credentials.json` and
`token.json` into the repository directory on the cluster (as in step 3),
then submit a job that activates the venv and runs the script directly:

```bash
#!/bin/bash
#SBATCH --job-name=mead-download
#SBATCH --nodes=1
#SBATCH --time=24:00:00
#SBATCH --output=mead-download_%j.out
#SBATCH --error=mead-download_%j.err
#SBATCH --mem=32G
#SBATCH --cpus-per-task=2

source .venv/bin/activate
python main_oauth.py
```

Adjust `--time` to your cluster's limits. Downloads are resumable (each file
is written to a `.part` file until complete), so if the job hits the
walltime limit partway through, simply resubmitting will pick up where it
left off.

### 5. Verify the download

After complete dataset download `verify.py` can be run to check each entry in
`mead_file_list.csv` against Google Drive without re-downloading any file
contents:

```bash
python verify.py
```

For each file it checks that the local file exists, compares its size and
MD5 checksum against Drive's metadata, and writes a row per file to
`mead_verification.csv` (updated continuously, so the report is preserved
even if the run is interrupted). It prints a summary of statuses (`OK`,
`MISSING`, `SIZE_MISMATCH`, `MD5_MISMATCH`, etc.) and exits non-zero if any
file needs attention, so it can be dropped into a script or a follow-up
SLURM job the same way as the download step. It only needs `token.json` (no
browser), so it can run anywhere `main_oauth.py` does.
