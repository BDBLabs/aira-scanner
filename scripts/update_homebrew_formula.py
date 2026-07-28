#!/usr/bin/env python3
"""Update the Homebrew formula to point at a new immutable GitHub archive."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


REPO = "BDBLabs/aira-scanner"
FORMULA_PATH = Path(__file__).resolve().parents[1] / "Formula" / "aira.rb"
VERSION_PATH = Path(__file__).resolve().parents[1] / "CLI" / "pyproject.toml"


def infer_version() -> str:
    content = VERSION_PATH.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', content, re.MULTILINE)
    if not match:
        raise SystemExit(f"Could not determine project version from {VERSION_PATH}")
    return match.group(1)


def archive_url(ref: str) -> str:
    normalized = ref.strip()
    if re.fullmatch(r"[0-9a-f]{40}", normalized):
        return f"https://github.com/{REPO}/archive/{normalized}.tar.gz"
    return f"https://github.com/{REPO}/archive/refs/tags/{normalized}.tar.gz"


def fetch_sha256(url: str) -> str:
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url) as response:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Could not download archive {url}: HTTP {exc.code}") from exc
    return digest.hexdigest()


def update_formula(url: str, version: str, sha256: str) -> None:
    content = FORMULA_PATH.read_text(encoding="utf-8")
    content, url_count = re.subn(r'^  url ".*"$', f'  url "{url}"', content, count=1, flags=re.MULTILINE)
    content, version_count = re.subn(r'^  version ".*"$', f'  version "{version}"', content, count=1, flags=re.MULTILINE)
    content, sha_count = re.subn(r'^  sha256 ".*"$', f'  sha256 "{sha256}"', content, count=1, flags=re.MULTILINE)
    if url_count != 1 or version_count != 1 or sha_count != 1:
        raise SystemExit(f"Could not update stable stanza in {FORMULA_PATH}")
    FORMULA_PATH.write_text(content, encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref", help="Git commit SHA or git tag to package")
    parser.add_argument("--version", default=infer_version(), help="Formula version to record (defaults to CLI package version)")
    args = parser.parse_args(argv)

    url = archive_url(args.ref)
    sha256 = fetch_sha256(url)
    update_formula(url, args.version, sha256)
    print(f"Updated {FORMULA_PATH}")
    print(f"  version: {args.version}")
    print(f"  url:     {url}")
    print(f"  sha256:  {sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
