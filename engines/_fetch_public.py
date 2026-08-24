"""One-shot downloader for public engine binaries. Not imported by the app."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
SEVEN_ZIP = Path(r"C:\Program Files\7-Zip\7z.exe")
USER_AGENT = "ChessCore-engine-fetch/1.0 (+https://github.com/official-stockfish/Stockfish)"

ENGINES = {
    "stockfish": {
        "url": "https://github.com/official-stockfish/Stockfish/releases/download/sf_18/stockfish-windows-x86-64-avx2.zip",
        "kind": "zip",
        "tag": "sf_18",
        "source": "https://github.com/official-stockfish/Stockfish/releases/tag/sf_18",
    },
    "yaneuraou": {
        "url": "https://github.com/yaneurao/YaneuraOu/releases/download/V9.00/yaneuraou-V900-git-win64-all.7z",
        "kind": "7z",
        "tag": "V9.00",
        "source": "https://github.com/yaneurao/YaneuraOu/releases/tag/V9.00",
    },
    "scan": {
        "url": "https://hjetten.home.xs4all.nl/scan/scan_31.zip",
        "kind": "zip",
        "tag": "3.1",
        "source": "https://github.com/rhalbersma/scan",
        "binary_host": "https://hjetten.home.xs4all.nl/scan/scan.html",
    },
}


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"GET {url}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out)
    print(f"saved {dest} ({dest.stat().st_size} bytes)", flush=True)


def extract_zip(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target)


def extract_7z(archive: Path, target: Path) -> None:
    if not SEVEN_ZIP.is_file():
        raise RuntimeError("7-Zip not found at C:\\Program Files\\7-Zip\\7z.exe")
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(SEVEN_ZIP), "x", str(archive), f"-o{target}", "-y"], check=True)


def pick_exe(extracted: Path, prefer: tuple[str, ...], fallback: tuple[str, ...] = ()) -> Path:
    exes = sorted(extracted.rglob("*.exe"))
    if not exes:
        raise FileNotFoundError(f"no .exe under {extracted}")
    lowered = [(path, path.name.lower()) for path in exes]
    for needle in prefer:
        matches = [path for path, name in lowered if needle in name]
        if matches:
            return matches[0]
    for needle in fallback:
        matches = [path for path, name in lowered if needle in name]
        if matches:
            return matches[0]
    return exes[0]


def flatten_scan(extracted: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    # scan_31.zip usually contains a single top-level folder.
    children = [p for p in extracted.iterdir() if p.name not in {".", ".."}]
    root = children[0] if len(children) == 1 and children[0].is_dir() else extracted
    for item in root.iterdir():
        target = dest / item.name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.move(str(item), str(target))
    exe = dest / "scan.exe"
    if not exe.is_file():
        found = pick_exe(dest, ("scan.exe",), ("scan",))
        exe = dest / "scan.exe"
        shutil.copy2(found, exe)
    return exe


def install_named_exe(extracted: Path, dest: Path, filename: str, prefer: tuple[str, ...], fallback: tuple[str, ...] = ()) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    chosen = pick_exe(extracted, prefer, fallback)
    target = dest / filename
    shutil.copy2(chosen, target)
    (dest / "UPSTREAM_EXE.txt").write_text(f"{chosen.name}\n", encoding="utf-8")
    return target


def write_origin(dest: Path, meta: dict) -> None:
    payload = {
        "downloaded_from": meta["url"],
        "release": meta["tag"],
        "source": meta["source"],
        "binary_host": meta.get("binary_host"),
    }
    (dest / "ORIGIN.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (ROOT / "custom").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="chess-core-engines-") as tmp:
        tmp_path = Path(tmp)
        archives = tmp_path / "archives"
        extracted = tmp_path / "extracted"

        for name, meta in ENGINES.items():
            archive = archives / Path(meta["url"]).name
            unpack = extracted / name
            dest = PUBLIC / name
            dest.mkdir(parents=True, exist_ok=True)
            download(meta["url"], archive)
            if meta["kind"] == "zip":
                extract_zip(archive, unpack)
            else:
                extract_7z(archive, unpack)
            write_origin(dest, meta)
            if name == "stockfish":
                exe = install_named_exe(
                    unpack,
                    dest,
                    "stockfish.exe",
                    ("avx2",),
                    ("stockfish",),
                )
            elif name == "yaneuraou":
                exe = install_named_exe(
                    unpack,
                    dest,
                    "yaneuraou.exe",
                    ("nnue-avx2", "nnue_avx2", "avx2"),
                    ("nnue", "yaneura"),
                )
                # Keep a material engine too: it talks USI without a huge eval file.
                try:
                    material = pick_exe(unpack, ("material-avx2", "material_avx2", "material"), ())
                    shutil.copy2(material, dest / "yaneuraou-material.exe")
                except FileNotFoundError:
                    pass
            else:
                exe = flatten_scan(unpack, dest)
            print(f"{name} executable: {exe} ({exe.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
