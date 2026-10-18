"""Train a CUDA CNN on chess-notation glyphs.

Requires Python 3.11+ and a CUDA build of PyTorch. EMNIST is inverted to
dark ink on white 28×28, matching scoresheet ``mnist_pad`` tiles.
Training adds strikethroughs, stroke thicken/thin, affine warp, blur and noise.

    python -m chess_core.tools.train_glyph_cnn
    python -m chess_core.tools.train_glyph_cnn --preview-only
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:32")

import numpy as np

from chess_core.app.experiments.ocr_glyphs import (
    CHARSET,
    CYRILLIC_ROLES,
    augment_mnist_glyph,
    class_weights,
    make_glyph_cnn,
    collect_cyrillic_paths,
    cyrillic_root,
    emnist_keep_indices,
    emnist_root,
    group_emnist,
    load_cyrillic_labeled,
    load_features_warm_start,
    missing_cyrillic,
    weights_dir,
)
from chess_core.infra.paths import project_root
from chess_core.ocr.labels import migrate_labels_file
from chess_core.ocr.roles import ROLE_IDS, labels_v2_payload
from chess_core.ocr.split import (
    SplitRecord,
    assert_hash_disjoint,
    assert_writer_disjoint,
    oversample_indices,
    tile_hash,
    write_split,
)

_TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu128"
_COMNIST_REPO = "FrancophonIA/CoMNIST"
_CYRILLIC_ZIP = (
    "https://raw.githubusercontent.com/degtya/HandwrittenCyrillicDataset/"
    "main/processed_cyrillic_dataset.zip"
)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _require_python() -> None:
    if sys.version_info < (3, 11):
        raise SystemExit(f"нужен Python 3.11 или новее, сейчас {sys.version}")


def _install_cuda_torch() -> None:
    print(f"ставим torch/torchvision с CUDA (cu128) в Python {sys.version.split()[0]}…")
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "torch",
            "torchvision",
            "--index-url",
            _TORCH_CUDA_INDEX,
        ]
    )


def ensure_cuda_torch():
    """Install a CUDA build of PyTorch into this interpreter, then require a GPU."""

    _require_python()
    try:
        import torch
    except ImportError:
        _install_cuda_torch()
        import torch
    if not torch.cuda.is_available():
        print("в этом интерпретаторе нет CUDA — ставим GPU-сборку заново…")
        _install_cuda_torch()
        import importlib

        import torch

        importlib.reload(torch)
    if not torch.cuda.is_available():
        raise SystemExit(
            "нужна CUDA. Переустановите: "
            f"{sys.executable} -m pip install torch torchvision "
            f"--index-url {_TORCH_CUDA_INDEX}"
        )
    torch.cuda.set_per_process_memory_fraction(0.65)
    print(
        f"torch={torch.__version__} cuda={torch.version.cuda} "
        f"device={torch.cuda.get_device_name(0)} "
        f"vram={torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)}MiB"
    )
    return torch


def load_emnist_split(*, train: bool):
    from torchvision.datasets import EMNIST

    keep = emnist_keep_indices()
    root = emnist_root()
    root.mkdir(parents=True, exist_ok=True)
    dataset = EMNIST(
        root=str(root),
        split="byclass",
        train=train,
        download=True,
    )
    data = dataset.data.numpy() if hasattr(dataset.data, "numpy") else np.asarray(dataset.data)
    targets = (
        dataset.targets.numpy()
        if hasattr(dataset.targets, "numpy")
        else np.asarray(dataset.targets)
    )
    keep_ids = np.fromiter(keep.keys(), dtype=targets.dtype)
    mask = np.isin(targets, keep_ids)
    return group_emnist(data[mask], targets[mask], keep)


def _try_huggingface_comnist(dest: Path) -> Path | None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        from huggingface_hub import snapshot_download

    try:
        snapshot_download(
            repo_id=_COMNIST_REPO,
            repo_type="dataset",
            local_dir=str(dest / "comnist"),
        )
    except Exception as exc:
        print(f"CoMNIST с Hugging Face не скачался: {exc}")
        return None
    folder = dest / "comnist"
    found = collect_cyrillic_paths(folder)
    if all(found[role_id] for role_id in CYRILLIC_ROLES):
        return folder
    print("CoMNIST скачался, но папок Л/Ф/р в нём нет")
    return None


def _try_github_cyrillic(dest: Path) -> Path | None:
    import urllib.request

    archive = dest / "handwritten_cyrillic.zip"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"скачиваем запасной кириллический набор в {archive}")
    try:
        urllib.request.urlretrieve(_CYRILLIC_ZIP, archive)
    except Exception as exc:
        print(f"запасной набор не скачался: {exc}")
        return None
    extracted = dest / "handwritten_cyrillic"
    if extracted.exists():
        shutil.rmtree(extracted)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    found = collect_cyrillic_paths(extracted)
    if all(found[role_id] for role_id in CYRILLIC_ROLES):
        return extracted
    print("запасной архив есть, но папок Л/Ф/р в нём нет")
    return None


def ensure_cyrillic() -> Path | None:
    root = cyrillic_root()
    existing = collect_cyrillic_paths(root)
    if all(existing[role_id] for role_id in CYRILLIC_ROLES):
        return root
    print("кириллицы нет — пробуем CoMNIST, затем 28×28 набор с GitHub")
    loaded = _try_huggingface_comnist(root) or _try_github_cyrillic(root)
    if loaded is None:
        print(
            f"предупреждение: нет кириллического набора в {root}. "
            "Роли RK/QN/ER останутся только с латиницей (ER с support=0)."
        )
        return None
    return loaded


def _preview_sheet(by_label: dict, path: Path, *, charset: tuple[str, ...] = CHARSET, per_class: int = 2) -> None:
    import cv2

    tiles: list[np.ndarray] = []
    captions: list[str] = []
    for label in charset:
        items = by_label.get(label) or []
        if not items:
            continue
        for item in items[:per_class]:
            tiles.append(item)
            captions.append(label)
    if not tiles:
        return
    cell = 56
    cols = 8
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.full((rows * (cell + 18), cols * cell, 3), 240, dtype=np.uint8)
    for index, (tile, caption) in enumerate(zip(tiles, captions)):
        row, col = divmod(index, cols)
        y, x = row * (cell + 18), col * cell
        big = cv2.resize(tile, (cell - 4, cell - 4), interpolation=cv2.INTER_NEAREST)
        sheet[y + 2 : y + cell - 2, x + 2 : x + cell - 2] = cv2.cvtColor(big, cv2.COLOR_GRAY2BGR)
        cv2.putText(
            sheet,
            caption,
            (x + 4, y + cell + 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", sheet)[1].tofile(str(path))


def _split_train_val(images, labels, *, val_frac: float, rng: np.random.Generator):
    n = len(labels)
    perm = rng.permutation(n)
    n_val = max(1, int(round(n * val_frac)))
    val_idx, train_idx = perm[:n_val], perm[n_val:]
    return images[train_idx], labels[train_idx], images[val_idx], labels[val_idx]


def _accuracy_by_class(logits, labels, charset: tuple[str, ...]) -> dict[str, float]:
    pred = logits.argmax(dim=1)
    out: dict[str, float] = {}
    for index, char in enumerate(charset):
        mask = labels == index
        if int(mask.sum()) == 0:
            continue
        out[char] = float((pred[mask] == labels[mask]).float().mean())
    return out


def _error_sheet(images, labels, preds, path: Path, *, charset: tuple[str, ...] = CHARSET, limit: int = 48) -> None:
    import cv2

    wrong = np.where(labels != preds)[0][:limit]
    if wrong.size == 0:
        return
    tiles: list[np.ndarray] = []
    captions: list[str] = []
    for index in wrong:
        tile = images[index]
        if tile.ndim == 3:
            tile = tile[0]
        tiles.append((tile * 255.0).clip(0, 255).astype(np.uint8))
        captions.append(f"{charset[int(labels[index])]}>{charset[int(preds[index])]}")
    cell = 56
    cols = 8
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.full((rows * (cell + 18), cols * cell, 3), 240, dtype=np.uint8)
    for index, (tile, caption) in enumerate(zip(tiles, captions)):
        row, col = divmod(index, cols)
        y, x = row * (cell + 18), col * cell
        big = cv2.resize(tile, (cell - 4, cell - 4), interpolation=cv2.INTER_NEAREST)
        sheet[y + 2 : y + cell - 2, x + 2 : x + cell - 2] = cv2.cvtColor(big, cv2.COLOR_GRAY2BGR)
        cv2.putText(
            sheet,
            caption,
            (x + 2, y + cell + 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
    cv2.imencode(".png", sheet)[1].tofile(str(path))


class _GlyphDataset:
    def __init__(self, torch, images: np.ndarray, labels: np.ndarray, *, augment: bool) -> None:
        self._torch = torch
        self.images = images
        self.labels = labels
        self.augment = augment

    def __len__(self) -> int:
        return int(len(self.labels))

    def __getitem__(self, index: int):
        tile = self.images[index]
        if self.augment:
            tile = augment_mnist_glyph(tile)
        tensor = self._torch.from_numpy(np.ascontiguousarray(tile)).float().unsqueeze(0) / 255.0
        target = self._torch.tensor(int(self.labels[index]), dtype=self._torch.long)
        return tensor, target


def _upsample_min_count(
    images: np.ndarray,
    labels: np.ndarray,
    *,
    min_count: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    parts_x: list[np.ndarray] = []
    parts_y: list[np.ndarray] = []
    for cls in np.unique(labels):
        idx = np.where(labels == cls)[0]
        if len(idx) < min_count:
            extra = rng.choice(idx, size=min_count - len(idx), replace=True)
            idx = np.concatenate([idx, extra])
        parts_x.append(images[idx])
        parts_y.append(labels[idx])
    return np.concatenate(parts_x), np.concatenate(parts_y)


def train_loop(
    torch,
    model,
    train_loader,
    val_loader,
    weights,
    *,
    epochs: int,
    out_dir: Path,
    charset: tuple[str, ...] = CHARSET,
    on_checkpoint=None,
):
    device = torch.device("cuda")
    criterion = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(weights, device=device),
        label_smoothing=0.06,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    best_acc = -1.0
    history: list[dict] = []
    best_errors: tuple | None = None
    for epoch in range(1, epochs + 1):
        model.train()
        running = 0.0
        seen = 0
        for batch, target in train_loader:
            batch = batch.to(device, non_blocking=True)
            target = target.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch)
            loss = criterion(logits, target)
            loss.backward()
            optimizer.step()
            running += float(loss.item()) * int(target.size(0))
            seen += int(target.size(0))
            del logits, loss
        model.eval()
        correct = 0
        total = 0
        all_logits = []
        all_labels = []
        error_images: list = []
        error_labels: list[int] = []
        error_preds: list[int] = []
        with torch.no_grad():
            for batch, target in val_loader:
                images = batch.to(device, non_blocking=True)
                target_gpu = target.to(device, non_blocking=True)
                logits = model(images)
                pred = logits.argmax(dim=1)
                correct += int((pred == target_gpu).sum())
                total += int(target_gpu.size(0))
                all_logits.append(logits.detach().cpu())
                all_labels.append(target_gpu.detach().cpu())
                if len(error_images) < 48:
                    wrong = pred != target_gpu
                    if bool(wrong.any()):
                        take = 48 - len(error_images)
                        picked = batch[wrong.cpu()][:take]
                        error_images.append(picked.contiguous())
                        error_labels.extend(target[wrong.cpu()][:take].tolist())
                        error_preds.extend(pred[wrong][:take].cpu().tolist())
                del images, target_gpu, logits, pred
        acc = correct / max(total, 1)
        logits_cat = torch.cat(all_logits)
        labels_cat = torch.cat(all_labels)
        per_class = _accuracy_by_class(logits_cat, labels_cat, charset)
        del logits_cat, labels_cat, all_logits, all_labels
        row = {
            "epoch": epoch,
            "train_loss": running / max(seen, 1),
            "val_acc": acc,
            "per_class": {key: round(value, 4) for key, value in per_class.items()},
        }
        history.append(row)
        print(
            f"epoch {epoch}/{epochs} loss={row['train_loss']:.4f} "
            f"val_acc={acc:.4f} "
            + " ".join(f"{k}={v:.2f}" for k, v in per_class.items()),
            flush=True,
        )
        if acc > best_acc:
            best_acc = acc
            torch.save(model.state_dict(), out_dir / "glyph_cnn.pt")
            if error_images:
                best_errors = (
                    torch.cat(error_images).numpy(),
                    np.asarray(error_labels, dtype=np.int64),
                    np.asarray(error_preds, dtype=np.int64),
                )
        scheduler.step()
        torch.cuda.empty_cache()
        if on_checkpoint is not None:
            on_checkpoint(history, best_acc)
    if best_errors is not None:
        _error_sheet(*best_errors, path=out_dir / "errors.png", charset=charset)
    return history, best_acc


def _split_writers(writer_ids: list[str], *, val_frac: float, rng: np.random.Generator) -> tuple[set[str], set[str]]:
    unique = sorted(set(writer_ids))
    order = rng.permutation(len(unique))
    names = [unique[int(i)] for i in order]
    if len(names) == 1:
        return set(names), set()
    n_val = max(1, int(round(len(names) * val_frac)))
    n_val = min(n_val, len(names) - 1)
    return set(names[n_val:]), set(names[:n_val])


def _write_role_support(
    path: Path,
    train_counts: dict[str, int],
    val_counts: dict[str, int],
    warnings: list[str],
) -> None:
    rows = []
    for role_id in ROLE_IDS:
        support = int(train_counts.get(role_id, 0))
        row = {
            "id": role_id,
            "train": support,
            "val": int(val_counts.get(role_id, 0)),
            "support": support,
        }
        if support == 0:
            if role_id in {"PLUS", "HASH", "EQ"}:
                row["plan"] = (
                    "нет в EMNIST ByClass; вырезать +/#/= с бланков или нарисовать пером. "
                    "HASH — мат, не мусор сетки (клеточный гейт — P2)."
                )
            elif role_id == "ER":
                row["plan"] = "нужны глифы р/Р из кириллического набора (--no-latin-only)."
            else:
                row["plan"] = "добавить глифы этой роли из EMNIST/кириллицы, класс не создавать заново."
            warnings.append(f"роль {role_id}: support=0. {row['plan']}")
        elif support < 50:
            row["plan"] = "меньше 50 train-примеров; добрать того же писателя нельзя — нужен новый источник."
            warnings.append(f"роль {role_id}: support={support} < 50")
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"roles": rows, "warnings": warnings}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description="CUDA CNN по глифам шахматной нотации.")
    parser.add_argument("--epochs", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-per-class", type=int, default=4000)
    parser.add_argument("--val-frac", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument(
        "--latin-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="без кириллицы (латинский бланк). --no-latin-only добавляет Л/Ф/р/К/С в те же роли",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root() / "output" / "ocr_glyph_cnn",
    )
    args = parser.parse_args(argv)

    torch = ensure_cuda_torch()
    rng = np.random.default_rng(args.seed)
    charset = ROLE_IDS
    print("грузим EMNIST ByClass, official train/test (writer-disjoint в NIST)…")
    train_groups = load_emnist_split(train=True)
    val_groups = load_emnist_split(train=False)
    train_writers: dict[str, list[str]] = {
        role_id: ["emnist-official-train"] * len(train_groups.get(role_id, []))
        for role_id in ROLE_IDS
    }
    val_writers: dict[str, list[str]] = {
        role_id: ["emnist-official-test"] * len(val_groups.get(role_id, []))
        for role_id in ROLE_IDS
    }
    split_notes = [
        "EMNIST ByClass в torchvision не отдаёт writer id; берём official NIST train/test, они writer-disjoint.",
        "HASH/PLUS/EQ не синтезируем: это маркеры нотации, не мусор сетки.",
    ]
    if args.latin_only:
        print("кириллица пропущена (--latin-only)")
        split_notes.append("кириллица не загружена: --latin-only")
    else:
        cyr_dir = ensure_cyrillic()
        if cyr_dir is None:
            split_notes.append("кириллический набор не найден, ER вероятно support=0")
        else:
            cyr_groups, cyr_writer_map = load_cyrillic_labeled(cyr_dir)
            missing = missing_cyrillic(cyr_groups)
            if missing:
                print(f"предупреждение: нет кириллических глифов {', '.join(missing)} в {cyr_dir}")
            all_cyr_writers = [wid for role_id in ROLE_IDS for wid in cyr_writer_map.get(role_id, [])]
            cyr_train_w, cyr_val_w = _split_writers(all_cyr_writers, val_frac=args.val_frac, rng=rng)
            for role_id in ROLE_IDS:
                tiles = cyr_groups.get(role_id) or []
                wids = cyr_writer_map.get(role_id) or []
                for tile, writer_id in zip(tiles, wids):
                    if writer_id in cyr_val_w:
                        val_groups.setdefault(role_id, []).append(tile)
                        val_writers.setdefault(role_id, []).append(writer_id)
                    else:
                        train_groups.setdefault(role_id, []).append(tile)
                        train_writers.setdefault(role_id, []).append(writer_id)

    raw_train = {label: list(train_groups.get(label, [])) for label in charset}
    raw_val = {label: list(val_groups.get(label, [])) for label in charset}
    raw_counts = {label: len(raw_train.get(label, [])) for label in charset}
    print("support до oversample:", " ".join(f"{k}={v}" for k, v in raw_counts.items()))

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    val_counts = {k: len(raw_val.get(k, [])) for k in charset}
    _write_role_support(project_root() / "logs" / "role_support.json", raw_counts, val_counts, warnings)
    shutil.copyfile(project_root() / "logs" / "role_support.json", out_dir / "role_support.json")
    for line in warnings:
        print(f"предупреждение: {line}")

    train_images: list[np.ndarray] = []
    train_labels: list[int] = []
    train_writer_list: list[str] = []
    train_hash_list: list[str] = []
    for index, role_id in enumerate(charset):
        for tile, writer_id in zip(raw_train.get(role_id, []), train_writers.get(role_id, [])):
            train_images.append(tile)
            train_labels.append(index)
            train_writer_list.append(writer_id)
            train_hash_list.append(tile_hash(tile))
    val_images: list[np.ndarray] = []
    val_labels: list[int] = []
    val_writer_list: list[str] = []
    val_hash_list: list[str] = []
    for index, role_id in enumerate(charset):
        tiles = raw_val.get(role_id, [])
        wids = val_writers.get(role_id, ["emnist-official-test"] * len(tiles))
        for tile, writer_id in zip(tiles, wids):
            val_images.append(tile)
            val_labels.append(index)
            val_writer_list.append(writer_id)
            val_hash_list.append(tile_hash(tile))

    assert_writer_disjoint(train_writer_list, val_writer_list)
    val_hash_set = set(val_hash_list)
    leaked = [index for index, digest in enumerate(train_hash_list) if digest in val_hash_set]
    if leaked:
        print(f"предупреждение: {len(leaked)} train-тайлов совпали по хешу с val — убираем из train")
        keep = [index for index in range(len(train_hash_list)) if index not in set(leaked)]
        train_images = [train_images[index] for index in keep]
        train_labels = [train_labels[index] for index in keep]
        train_writer_list = [train_writer_list[index] for index in keep]
        train_hash_list = [train_hash_list[index] for index in keep]
        split_notes.append(f"dropped {len(leaked)} train tiles with val hash collision")
    assert_hash_disjoint(train_hash_list, val_hash_list)

    x_train = np.stack(train_images, axis=0) if train_images else np.zeros((0, 28, 28), np.uint8)
    y_train = np.asarray(train_labels, dtype=np.int64)
    x_val = np.stack(val_images, axis=0) if val_images else np.zeros((0, 28, 28), np.uint8)
    y_val = np.asarray(val_labels, dtype=np.int64)

    picked = oversample_indices(
        y_train,
        min_count=2000,
        cap=args.max_per_class,
        rng=rng,
    )
    pick_counts = Counter(int(i) for i in picked)
    oversampled_from = tuple(train_hash_list[i] for i, n in pick_counts.items() if n > 1)
    assert_hash_disjoint(oversampled_from, val_hash_list)

    x_train = x_train[picked]
    y_train = y_train[picked]
    train_hash_after = [train_hash_list[int(i)] for i in picked]
    train_writer_after = [train_writer_list[int(i)] for i in picked]

    val_cap = min(800, args.max_per_class)
    val_picked = oversample_indices(y_val, min_count=0, cap=val_cap, rng=rng)
    x_val = x_val[val_picked]
    y_val = y_val[val_picked]
    val_hash_after = [val_hash_list[int(i)] for i in val_picked]
    val_writer_after = [val_writer_list[int(i)] for i in val_picked]

    split_path = write_split(
        SplitRecord(
            seed=args.seed,
            method="emnist-official-train-test + cyrillic-writer-split",
            train_writers=tuple(sorted(set(train_writer_after))),
            val_writers=tuple(sorted(set(val_writer_after))),
            train_hashes=tuple(sorted(set(train_hash_after))),
            val_hashes=tuple(sorted(set(val_hash_after))),
            oversampled_hashes=tuple(sorted(set(oversampled_from))),
            notes=tuple(split_notes),
        )
    )
    print(f"split={split_path}")

    counts = {role_id: int((y_train == index).sum()) for index, role_id in enumerate(charset)}
    print("классы после oversample:", " ".join(f"{k}={v}" for k, v in counts.items()))

    preview_groups: dict[str, list] = {role_id: [] for role_id in charset}
    for tile, label in zip(x_train, y_train):
        bucket = preview_groups[charset[int(label)]]
        if len(bucket) < 2:
            bucket.append(tile)
    _preview_sheet(preview_groups, out_dir / "preview.png", charset=charset)
    print(f"preview={out_dir / 'preview.png'}")
    aug_preview = {
        label: [augment_mnist_glyph(item, rng) for item in items[:2]]
        for label, items in preview_groups.items()
        if items
    }
    _preview_sheet(aug_preview, out_dir / "preview_aug.png", charset=charset)
    print(f"preview_aug={out_dir / 'preview_aug.png'}")
    if args.preview_only:
        return 0

    weights = class_weights(y_train, len(charset))
    weights = np.minimum(weights, 1.5)

    labels_path = out_dir / "labels.json"
    if labels_path.is_file():
        migrate_labels_file(labels_path)

    def as_loader(x, y, *, shuffle: bool, augment: bool):
        dataset = _GlyphDataset(torch, x, y, augment=augment)
        return torch.utils.data.DataLoader(
            dataset,
            batch_size=args.batch_size,
            shuffle=shuffle,
            pin_memory=False,
            num_workers=0,
        )

    def write_labels(history: list, best_acc: float) -> None:
        payload = labels_v2_payload()
        payload.update(
            {
                "label_to_index": {role_id: index for index, role_id in enumerate(charset)},
                "counts": counts,
                "best_val_acc": best_acc,
                "history": history,
                "input": "1x28x28 dark ink on white, /255",
                "architecture": "64-64-128-128-256 conv, 512 head",
                "augment": "strikethrough, dilate/erode, affine, blur, noise",
                "epochs": args.epochs,
                "batch_size": args.batch_size,
                "seed": args.seed,
                "split": str(split_path),
                "note": (
                    "P1 роли, не Unicode. KN двусмыслен (N/K/К). "
                    "C/c больше не два класса: лат. c=f_c, C/С/B=BS. "
                    "HASH — мат, не мусор. val_acc несравним с EMNIST P0 0.982."
                ),
            }
        )
        (out_dir / "labels.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    model = make_glyph_cnn(torch, len(charset)).to(torch.device("cuda"))
    old_weights = (out_dir / "glyph_cnn.pt") if (out_dir / "glyph_cnn.pt").is_file() else (weights_dir() / "glyph_cnn.pt")
    if old_weights.is_file():
        print(f"warm-start conv из {old_weights}")
        load_features_warm_start(model, old_weights, torch)
    history, best_acc = train_loop(
        torch,
        model,
        as_loader(x_train, y_train, shuffle=True, augment=True),
        as_loader(x_val, y_val, shuffle=False, augment=False),
        weights,
        epochs=args.epochs,
        out_dir=out_dir,
        charset=charset,
        on_checkpoint=write_labels,
    )
    write_labels(history, best_acc)
    print(f"weights={out_dir / 'glyph_cnn.pt'}")
    print(f"labels={out_dir / 'labels.json'}")
    print(f"best_val_acc={best_acc:.4f}  (пространство ролей, не сравнивать с P0 EMNIST 0.982)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
