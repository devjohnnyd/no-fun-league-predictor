"""Public data acquisition. Each bundle is a new, independently dated retrieval."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RELEASES = "https://github.com/nflverse/nflverse-data/releases/download"


def catalog(start, end):
    if not 2022 <= start <= end <= datetime.now(timezone.utc).year:
        raise ValueError("Choose seasons from 2022 through the current year")
    jobs = [
        ("schedule.csv", "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv", True),
        ("players.csv", RELEASES + "/players/players.csv", True),
    ]
    for season in range(start, end + 1):
        jobs += [
            (f"pbp_{season}.csv.gz", f"{RELEASES}/pbp/play_by_play_{season}.csv.gz", True),
            (f"snaps_{season}.csv", f"{RELEASES}/snap_counts/snap_counts_{season}.csv", True),
            (f"injuries_{season}.csv", f"{RELEASES}/injuries/injuries_{season}.csv", False),
            (f"ftn_{season}.csv", f"{RELEASES}/ftn_charting/ftn_charting_{season}.csv", False),
            (f"pfr_pass_{season}.csv", f"{RELEASES}/pfr_advstats/advstats_week_pass_{season}.csv", False),
        ]
    jobs += [(f"ngs_{kind}.csv.gz", f"{RELEASES}/nextgen_stats/ngs_{kind}.csv.gz", False)
             for kind in ("passing", "receiving", "rushing")]
    return jobs


def download(job, output):
    name, url, required = job
    destination = output / name
    receipt = {"file": name, "url": url, "required": required}
    if destination.exists():
        raise FileExistsError(destination)
    last_error = "Download failed"
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers={"User-Agent": "NoFunLeaguePredictor/4.0"}), timeout=45) as response:
                data = response.read()
                source_modified = response.headers.get("Last-Modified")
            if not data or data.lstrip().startswith((b"<html", b"<!DOCTYPE")):
                raise ValueError("Empty response or HTML in a data download")
            with destination.open("xb") as stream:
                stream.write(data)
            return {**receipt, "status": "ok", "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "source_last_modified": source_modified}
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            last_error = str(error)
            if isinstance(error, HTTPError) and error.code in (401, 403, 404):
                break
    return {**receipt, "status": "error", "error": last_error,
            "attempted_at": datetime.now(timezone.utc).isoformat()}


def acquire(start, end, output, only=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    jobs = catalog(start, end)
    if only == "ngs":
        jobs = [job for job in jobs if job[0].startswith("ngs_")]
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda job: download(job, output), jobs))
    manifest = {"version": 1, "start_season": start, "end_season": end,
                "created_at": datetime.now(timezone.utc).isoformat(), "sources": receipts,
                "attribution": "FTN Data via nflverse (ftndata.com); charting and its derivatives: CC-BY-SA 4.0"}
    (output / "sources.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    failures = [r["file"] for r in receipts if r["required"] and r["status"] != "ok"]
    if failures:
        raise RuntimeError("Required downloads failed: " + ", ".join(failures))
    return manifest
