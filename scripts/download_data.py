"""Download the official MOOCCubeX payloads needed by LearnPath."""

from __future__ import annotations

import argparse
import os
import re
import urllib.request
from pathlib import Path

BASE = "https://lfs.aminer.cn/misc/moocdata/data/mooccube2"


def files_for(domain: str, include_interactions: bool) -> list[str]:
    if domain not in ("cs", "math", "psy"):
        raise ValueError("domain must be cs, math, or psy")
    result = ["entities/concept.json", "relations/concept-problem.txt", f"prerequisites/{domain}.json"]
    if include_interactions:
        result.append("relations/user-problem.json")
    return result


def download_file(relative_path: str, root: Path, base: str = BASE, *, force: bool = False) -> Path:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size and not force:
        print(f"Already present: {relative_path} ({target.stat().st_size} bytes); use --force to replace")
        return target
    partial = target.with_name(target.name + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    request = urllib.request.Request(f"{base.rstrip('/')}/{relative_path}", headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        status = response.status
        mode = "wb"
        expected_total = None
        if offset and status == 206:
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", response.headers.get("Content-Range", ""))
            if not match or int(match.group(1)) != offset:
                raise OSError(f"Invalid Content-Range while resuming {relative_path}")
            expected_total = None if match.group(3) == "*" else int(match.group(3))
            mode = "ab"
        elif status == 200:
            expected_total = int(response.headers["Content-Length"]) if response.headers.get("Content-Length", "").isdigit() else None
        else:
            raise OSError(f"Unexpected HTTP status {status} for {relative_path}")
        with partial.open(mode) as output:
            while block := response.read(1024 * 1024):
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
    if expected_total is not None and partial.stat().st_size != expected_total:
        raise OSError(f"Incomplete download for {relative_path}: {partial.stat().st_size}/{expected_total} bytes")
    os.replace(partial, target)
    print(f"Downloaded {relative_path} ({target.stat().st_size} bytes)")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/mooccubex"))
    parser.add_argument("--domain", choices=("cs", "math", "psy"), default="cs")
    parser.add_argument("--include-interactions", action="store_true",
                        help="download user-problem.json (about 21 GB); required to run the pipeline")
    parser.add_argument("--force", action="store_true", help="replace files already downloaded")
    args = parser.parse_args()
    for relative_path in files_for(args.domain, args.include_interactions):
        download_file(relative_path, args.root, force=args.force)


if __name__ == "__main__":
    main()
