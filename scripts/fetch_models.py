#!/usr/bin/env python3
"""Explicit, atomic public-model setup. Normal runtime never calls this script.

OpenCV and Piper are resolved to immutable upstream revisions; LFS payloads
are verified against upstream object hashes. Vosk has no published immutable
revision/checksum API here: its first trusted TLS download is hashed and this
trust-on-first-download limitation is recorded in the manifest.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

MAX_DOWNLOAD = 512 * 1024 * 1024
ALLOWED_HOSTS = {
    "api.github.com",
    "raw.githubusercontent.com",
    "media.githubusercontent.com",
    "huggingface.co",
    "alphacephei.com",
}
VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
OPENCV_REPO = "opencv/opencv_zoo"
PIPER_REPO = "rhasspy/piper-voices"
PIPER_PREFIX = "en/en_US/lessac/medium/"


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not (host in ALLOWED_HOSTS or host.endswith(".hf.co"))
    ):
        raise ValueError("Only official HTTPS model hosts are allowed")
    return url


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def request(url):
    validate_url(url)
    opener = urllib.request.build_opener(OfficialRedirect())
    return opener.open(
        urllib.request.Request(
            url,
            headers={
                "User-Agent": "CogniSight-model-setup/0.1",
                "Accept": (
                    "application/json" if "/api/" in url or "api.github.com" in url else "*/*"
                ),
            },
        ),
        timeout=60,
    )


def read_bytes(url, maximum=16 * 1024 * 1024):
    with request(url) as response:
        payload = response.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError("Upstream metadata exceeds maximum size")
    return payload


def metadata(url):
    return json.loads(read_bytes(url))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lfs_oid(pointer):
    match = re.search(rb"^oid sha256:([a-f0-9]{64})$", pointer, re.MULTILINE)
    if not pointer.startswith(b"version https://git-lfs.github.com/spec/v1\n") or not match:
        raise ValueError("Upstream model is not a verifiable Git LFS pointer")
    return match[1].decode("ascii")


def download(url, path, expected=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with request(url) as response, path.open("xb") as output:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            size += len(chunk)
            if size > MAX_DOWNLOAD:
                raise ValueError("Model download exceeds maximum size")
            output.write(chunk)
    digest = sha256(path)
    if expected and digest != expected:
        raise ValueError("Downloaded model does not match upstream SHA-256")
    if size == 0:
        raise ValueError("Upstream returned an empty model")
    return digest


def safe_extract(source, destination, max_total=512 * 1024 * 1024):
    """Reject traversal, links, devices, duplicates, and oversized zip archives."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    files = []
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if len(members) > 4096:
            raise ValueError("Too many model archive members")
        total, seen = 0, set()
        for item in members:
            name = item.filename
            path = PurePosixPath(name)
            mode = item.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if (
                not name
                or "\\" in name
                or ":" in name
                or path.is_absolute()
                or ".." in path.parts
                or "\x00" in name
                or file_type not in (0, stat.S_IFREG, stat.S_IFDIR)
                or name in seen
            ):
                raise ValueError("Unsafe or duplicate model archive path")
            seen.add(name)
            target = destination.joinpath(*path.parts)
            if not target.resolve().is_relative_to(destination):
                raise ValueError("Model archive path escapes destination")
            if item.file_size > 128 * 1024 * 1024 or item.flag_bits & 1:
                raise ValueError("Oversized or encrypted model archive member")
            total += item.file_size
            if total > max_total:
                raise ValueError("Model archive exceeds extraction size limit")
        for item in members:
            target = destination.joinpath(*PurePosixPath(item.filename).parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            actual_size = 0
            with archive.open(item) as stream, target.open("xb") as output:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    actual_size += len(chunk)
                    if actual_size > item.file_size:
                        raise ValueError("Model archive expanded beyond declared size")
                    output.write(chunk)
            files.append(target)
    return files


def fetch(destination):
    destination = Path(destination).expanduser().resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError(
            "Destination must be absent or an empty directory; models are never overwritten"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".cognisight-models-", dir=destination.parent
    ) as directory:
        root = Path(directory) / "models"
        root.mkdir()
        manifest = {"schema_version": 1, "files": [], "sources": {}}

        def record(path, source):
            manifest["files"].append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256(path),
                    "source": source,
                }
            )

        commit = metadata("https://api.github.com/repos/" + OPENCV_REPO + "/commits/main")["sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise ValueError("Invalid OpenCV revision from upstream")
        assets = (
            ("face_detection_yunet", "face_detection_yunet_2023mar.onnx"),
            ("face_recognition_sface", "face_recognition_sface_2021dec.onnx"),
        )
        recognizer_hash = None
        for model_dir, name in assets:
            remote = "models/" + model_dir + "/" + name
            raw = "https://raw.githubusercontent.com/" + OPENCV_REPO + "/" + commit + "/" + remote
            expected = lfs_oid(read_bytes(raw, 4096))
            url = (
                "https://media.githubusercontent.com/media/"
                + OPENCV_REPO
                + "/"
                + commit
                + "/"
                + remote
            )
            path = root / name
            digest = download(url, path, expected)
            record(path, url)
            if model_dir == "face_recognition_sface":
                recognizer_hash = digest
        manifest["sources"]["opencv"] = {
            "revision": commit,
            "repository": OPENCV_REPO,
            "licenses": {"YuNet": "MIT", "SFace": "Apache-2.0"},
        }

        piper = metadata(
            "https://huggingface.co/api/models/" + PIPER_REPO + "/revision/main?blobs=true"
        )
        revision = piper["sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("Invalid Piper voice revision from upstream")
        siblings = {item["rfilename"]: item for item in piper["siblings"]}
        for name in ("en_US-lessac-medium.onnx", "en_US-lessac-medium.onnx.json", "MODEL_CARD"):
            remote = PIPER_PREFIX + name
            item = siblings.get(remote)
            if item is None:
                raise ValueError("Piper voice metadata does not contain required asset")
            lfs = item.get("lfs") or {}
            expected = lfs.get("sha256") or lfs.get("oid")
            if expected and not re.fullmatch(r"[a-f0-9]{64}", expected):
                raise ValueError("Invalid Piper upstream LFS hash")
            url = "https://huggingface.co/" + PIPER_REPO + "/resolve/" + revision + "/" + remote
            path = root / ("piper-MODEL_CARD" if name == "MODEL_CARD" else name)
            download(url, path, expected)
            blob = item.get("blobId")
            if not expected and blob:
                payload = path.read_bytes()
                git_hash = hashlib.sha1(
                    b"blob " + str(len(payload)).encode() + b"\x00" + payload
                ).hexdigest()
                if git_hash != blob:
                    raise ValueError("Piper metadata blob integrity mismatch")
            record(path, url)
        manifest["sources"]["piper_voice"] = {
            "revision": revision,
            "repository": PIPER_REPO,
            "model_card": "piper-MODEL_CARD",
            "license_note": "Retain upstream MODEL_CARD; Piper engine is GPL-3.0.",
        }

        archive = Path(directory) / "vosk.zip"
        archive_hash = download(VOSK_URL, archive)
        extracted = safe_extract(archive, root)
        if (
            not extracted
            or not (root / "vosk-model-small-en-us-0.15" / "conf" / "model.conf").is_file()
        ):
            raise ValueError("Vosk archive does not contain expected model layout")
        for path in extracted:
            record(path, VOSK_URL)
        manifest["sources"]["vosk"] = {
            "url": VOSK_URL,
            "archive_sha256": archive_hash,
            "license": "Apache-2.0",
            "verification": "First TLS download; upstream checksum not independently published here.",
        }
        manifest["model_version"] = "sface:" + recognizer_hash
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if destination.exists():
            destination.rmdir()  # Only succeeds if still empty; never overwrite concurrent content.
        os.rename(root, destination)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = fetch(args.destination)
    except Exception as exc:
        print("Model setup failed: " + str(exc), file=sys.stderr)
        return 1
    print("Models installed at " + str(args.destination.resolve()))
    print("model_version = " + manifest["model_version"])
    print("Use manifest.json to verify every runtime model file. No runtime downloads are needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
