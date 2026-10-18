"""One-shot downloader for public engine binaries. Not imported by the app."""

from __future__ import annotations

import hashlib
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
    "fairystockfish": {
        "url": "https://github.com/fairy-stockfish/Fairy-Stockfish/releases/download/fairy_sf_14/fairy-stockfish-largeboard_x86-64.exe",
        "kind": "exe",
        "tag": "fairy_sf_14",
        "source": "https://github.com/fairy-stockfish/Fairy-Stockfish/releases/tag/fairy_sf_14",
        "filename": "fairy-stockfish.exe",
        "variants_url": "https://github.com/fairy-stockfish/Fairy-Stockfish/releases/download/fairy_sf_14/variants.ini",
    },
    "fairystockfish-all": {
        "url": "https://github.com/gbtami/Fairy-Stockfish/releases/download/fishnet-260826/stockfish-windows-amd64.exe",
        "kind": "exe",
        "tag": "fishnet-260826",
        "source": "https://github.com/gbtami/Fairy-Stockfish/commit/43b66c8abfebfcab893a3a4c349aa790d18df148",
        "filename": "fairy-stockfish-all.exe",
        "sha256": "dd2152ba82fe1787d81ec4c42acdfdbaaa97088ba059cab5d77eadfaece23127",
    },
    "yaneuraou": {
        "url": "https://github.com/yaneurao/YaneuraOu/releases/download/V9.00/yaneuraou-V900-git-win64-all.7z",
        "kind": "7z",
        "tag": "V9.00",
        "source": "https://github.com/yaneurao/YaneuraOu/releases/tag/V9.00",
    },
}


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"GET {url}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out)
    print(f"saved {dest} ({dest.stat().st_size} bytes)", flush=True)


def verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest.lower() != expected.lower():
        raise RuntimeError(f"sha256 mismatch for {path.name}: {digest} != {expected}")


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
    wanted = set(sys.argv[1:]) or set(ENGINES)
    unknown = wanted - set(ENGINES)
    if unknown:
        raise SystemExit(f"unknown engines: {', '.join(sorted(unknown))}")
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (ROOT / "custom").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="chess-core-engines-") as tmp:
        tmp_path = Path(tmp)
        archives = tmp_path / "archives"
        extracted = tmp_path / "extracted"

        for name, meta in ENGINES.items():
            if name not in wanted:
                continue
            archive = archives / Path(meta["url"]).name
            unpack = extracted / name
            dest = PUBLIC / name
            dest.mkdir(parents=True, exist_ok=True)
            if meta["kind"] == "exe":
                dest_exe = dest / meta.get("filename", "engine.exe")
                download(meta["url"], dest_exe)
                if expected := meta.get("sha256"):
                    verify_sha256(dest_exe, expected)
                if variants_url := meta.get("variants_url"):
                    download(variants_url, dest / "variants.ini")
                write_origin(dest, meta)
                print(f"{name} executable: {dest_exe} ({dest_exe.stat().st_size} bytes)", flush=True)
                continue
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
                raise RuntimeError(f"unsupported engine package: {name}")
            print(f"{name} executable: {exe} ({exe.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
