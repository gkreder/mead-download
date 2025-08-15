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
