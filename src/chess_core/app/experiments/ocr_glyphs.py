"""Chess-notation glyph classes and MNIST-shaped training samples.

One 28×28 tile is one character. ``Кр`` is two glyphs (K then р), not a class.
EMNIST ByClass is inverted from white-on-black to dark ink on white paper,
then passed through the same ``mnist_pad`` as scoresheet crops.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from chess_core.app.experiments.ocr_mser import mnist_pad, to_gray
from chess_core.infra.paths import project_root
from chess_core.ocr.roles import ROLE_BY_ID, ROLE_IDS, canonicalize, try_canonicalize

LATIN_LETTERS = tuple("abcdefghNKBRQxO")
DIGITS = tuple("12345678")
CYRILLIC_LETTERS = ("Л", "Ф", "р")
CYRILLIC_ROLES = ("RK", "QN", "ER")
GARBAGE = "#"
CHARSET = ROLE_IDS
CHARSET_LATIN = ROLE_IDS
LABEL_TO_INDEX = {role_id: index for index, role_id in enumerate(ROLE_IDS)}
READ_EQUIV: dict[str, str] = {}
MIN_GLYPH_SCORE = 0.4
CYRILLIC_MIN_SCORE = 0.85

_CYRILLIC_FOLDER_ALIASES = {
    "Л": ("Л", "л"),
    "Ф": ("Ф", "ф"),
    "р": ("р", "Р"),
    "К": ("К", "к"),
    "С": ("С", "с"),
}


def glyph_data_root() -> Path:
    return project_root() / "data" / "experiments" / "ocr"


def emnist_root() -> Path:
    return glyph_data_root() / "emnist"


def cyrillic_root() -> Path:
    return glyph_data_root() / "cyrillic"


def emnist_byclass_index(char: str) -> int:
    """EMNIST ByClass label: 0–9 digits, 10–35 A–Z, 36–61 a–z."""

    if len(char) != 1:
        raise ValueError(char)
    if char.isdigit():
        return ord(char) - ord("0")
    if "A" <= char <= "Z":
        return 10 + ord(char) - ord("A")
    if "a" <= char <= "z":
        return 36 + ord(char) - ord("a")
    raise ValueError(char)


def emnist_keep_indices() -> dict[int, str]:
    """EMNIST ByClass index → role id. Both cases of a letter collapse only when they share a role."""

    glyphs = []
    for code in range(ord("0"), ord("9")):
        glyphs.append(chr(code))
    glyphs.extend(chr(code) for code in range(ord("A"), ord("Z") + 1))
    glyphs.extend(chr(code) for code in range(ord("a"), ord("z") + 1))
    keep: dict[int, str] = {}
    for char in glyphs:
        role_id = try_canonicalize(char)
        if role_id is None:
            continue
        keep[emnist_byclass_index(char)] = role_id
    return keep


def fix_emnist_orientation(image: np.ndarray) -> np.ndarray:
    """Undo the NIST column-major storage (transpose)."""

    gray = to_gray(image)
    return np.ascontiguousarray(np.transpose(gray))


def invert_to_dark_ink(image: np.ndarray) -> np.ndarray:
    """EMNIST/MNIST store ink as light pixels on a dark field."""

    gray = to_gray(image)
    return np.ascontiguousarray(255 - gray)


def ensure_dark_ink_on_white(image: np.ndarray) -> np.ndarray:
    gray = to_gray(image)
    if gray.size == 0:
        return gray
    h, w = gray.shape
    corner = int(
        np.mean(
            [
                gray[:2, :2].mean(),
                gray[:2, w - 2 :].mean(),
                gray[h - 2 :, :2].mean(),
                gray[h - 2 :, w - 2 :].mean(),
            ]
        )
    )
    if corner < 127:
        return invert_to_dark_ink(gray)
    return gray


def to_mnist_glyph(image: np.ndarray, *, invert: bool = False) -> np.ndarray:
    """``invert`` is for EMNIST/MNIST tensors. torchvision already transposes EMNIST."""

    gray = to_gray(image)
    if invert:
        gray = invert_to_dark_ink(gray)
    else:
        gray = ensure_dark_ink_on_white(gray)
    return mnist_pad(gray)


def thicken_strokes(tile: np.ndarray, *, size: int = 2) -> np.ndarray:
    """Widen dark ink (dilation). Scoresheet pens are thicker than EMNIST."""

    import cv2

    gray = to_gray(tile)
    k = max(2, int(size))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    ink = cv2.dilate(255 - gray, kernel, iterations=1)
    return np.clip(255 - ink, 0, 255).astype(np.uint8)


def thin_strokes(tile: np.ndarray, *, size: int = 2) -> np.ndarray:
    """Narrow dark ink (erosion). Keep the original if the glyph would vanish."""

    import cv2

    gray = to_gray(tile)
    k = max(2, int(size))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    ink = cv2.erode(255 - gray, kernel, iterations=1)
    if int(ink.max()) < 40:
        return gray
    return np.clip(255 - ink, 0, 255).astype(np.uint8)


def add_strikethrough(tile: np.ndarray, rng: np.random.Generator | None = None) -> np.ndarray:
    """One or two correction strokes, as on a scoresheet after a written-over move."""

    import cv2

    rng = rng or np.random.default_rng()
    out = to_gray(tile).copy()
    height, width = out.shape
    n_lines = 1 if rng.random() < 0.65 else 2
    for _ in range(n_lines):
        thickness = int(rng.integers(1, 3))
        color = int(rng.integers(0, 50))
        kind = float(rng.random())
        if kind < 0.55:
            y1 = int(rng.integers(height * 28 // 100, height * 72 // 100))
            y2 = int(np.clip(y1 + int(rng.integers(-6, 7)), 1, height - 2))
            cv2.line(out, (1, y1), (width - 2, y2), color, thickness, cv2.LINE_AA)
        elif kind < 0.8:
            cv2.line(out, (2, 2), (width - 3, height - 3), color, thickness, cv2.LINE_AA)
        else:
            cv2.line(out, (2, height - 3), (width - 3, 2), color, thickness, cv2.LINE_AA)
    return out


def augment_mnist_glyph(
    tile: np.ndarray,
    rng: np.random.Generator | None = None,
    *,
    strikethrough_p: float = 0.2,
) -> np.ndarray:
    """Match real blanks: thickness, strike-through, affine warp, blur, noise."""

    import cv2

    rng = rng or np.random.default_rng()
    out = to_gray(tile).copy()
    morph = float(rng.random())
    if morph < 0.30:
        out = thicken_strokes(out, size=int(rng.integers(2, 4)))
    elif morph < 0.52:
        out = thin_strokes(out, size=2)
    elif morph < 0.64:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        ink = cv2.morphologyEx(255 - out, cv2.MORPH_CLOSE, kernel)
        out = np.clip(255 - ink, 0, 255).astype(np.uint8)
    if rng.random() < strikethrough_p:
        out = add_strikethrough(out, rng)
    out = _random_affine(out, rng)
    out = mnist_pad(out)
    if rng.random() < 0.35:
        ksize = 3 if rng.random() < 0.7 else 5
        out = cv2.GaussianBlur(out, (ksize, ksize), 0)
    if rng.random() < 0.40:
        noise = rng.normal(0.0, 9.0, out.shape)
        out = np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    contrast = float(rng.uniform(0.72, 1.35))
    ink = np.clip((255.0 - out.astype(np.float32)) * contrast, 0, 255)
    return np.clip(255.0 - ink, 0, 255).astype(np.uint8)


def _random_affine(tile: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    import cv2

    height, width = tile.shape
    angle = float(rng.uniform(-8.0, 8.0))
    scale = float(rng.uniform(0.88, 1.12))
    shift_x = float(rng.uniform(-0.06, 0.06) * width)
    shift_y = float(rng.uniform(-0.06, 0.06) * height)
    shear = float(rng.uniform(-0.08, 0.08))
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, scale)
    matrix[0, 1] += shear
    matrix[0, 2] += shift_x
    matrix[1, 2] += shift_y
    return cv2.warpAffine(
        tile,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def make_garbage_tiles(count: int, rng: np.random.Generator) -> list[np.ndarray]:
    """Grid rules, specks and empty paper — reject class, not a chess letter."""

    import cv2

    tiles: list[np.ndarray] = []
    for _ in range(count):
        canvas = np.full((28, 28), 255, dtype=np.uint8)
        kind = float(rng.random())
        ink = int(rng.integers(0, 70))
        if kind < 0.28:
            y = int(rng.integers(6, 22))
            thickness = int(rng.integers(1, 3))
            canvas[y : y + thickness, 1:27] = ink
        elif kind < 0.5:
            x = int(rng.integers(6, 22))
            thickness = int(rng.integers(1, 3))
            canvas[1:27, x : x + thickness] = ink
        elif kind < 0.72:
            for _speck in range(int(rng.integers(4, 14))):
                yy = int(rng.integers(2, 26))
                xx = int(rng.integers(2, 26))
                canvas[yy : yy + 1, xx : xx + 1] = ink
        elif kind < 0.88:
            cv2.line(
                canvas,
                (int(rng.integers(0, 8)), int(rng.integers(0, 8))),
                (int(rng.integers(20, 28)), int(rng.integers(20, 28))),
                ink,
                1,
                cv2.LINE_AA,
            )
        tiles.append(mnist_pad(canvas))
    return tiles


def collect_cyrillic_paths(root: Path) -> dict[str, list[Path]]:
    """Map folder names to role ids (Л→RK, Ф→QN, К→KN, С→BS, р→ER)."""

    found: dict[str, list[Path]] = {role_id: [] for role_id in ROLE_IDS}
    if not root.is_dir():
        return found
    suffixes = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    alias_to_glyph = {
        alias: letter
        for letter, aliases in _CYRILLIC_FOLDER_ALIASES.items()
        for alias in aliases
    }
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        folder = path.parent.name
        glyph = alias_to_glyph.get(folder, folder)
        role_id = try_canonicalize(glyph)
        if role_id is None:
            continue
        found[role_id].append(path)
    return found


def load_cyrillic_glyphs(root: Path) -> dict[str, list[np.ndarray]]:
    samples, _writers = load_cyrillic_labeled(root)
    return samples


def load_cyrillic_labeled(root: Path) -> tuple[dict[str, list[np.ndarray]], dict[str, list[str]]]:
    samples: dict[str, list[np.ndarray]] = {role_id: [] for role_id in ROLE_IDS}
    writers: dict[str, list[str]] = {role_id: [] for role_id in ROLE_IDS}
    for role_id, paths in collect_cyrillic_paths(root).items():
        for path in paths:
            image = _read_gray(path)
            if image is None:
                continue
            samples[role_id].append(to_mnist_glyph(image, invert=False))
            writers[role_id].append(_cyrillic_writer_id(path))
    return samples, writers


def _cyrillic_writer_id(path: Path) -> str:
    return f"{path.parent.parent.name}/{path.parent.name}/{path.stem.split('_')[0]}"


def missing_cyrillic(samples: dict[str, list[np.ndarray]]) -> tuple[str, ...]:
    return tuple(role_id for role_id in CYRILLIC_ROLES if not samples.get(role_id))


def subsample_balanced(
    by_label: dict[str, list[np.ndarray]],
    *,
    max_per_class: int,
    rng: np.random.Generator,
) -> dict[str, list[np.ndarray]]:
    out: dict[str, list[np.ndarray]] = {}
    for label, items in by_label.items():
        if len(items) <= max_per_class:
            out[label] = list(items)
            continue
        choice = rng.choice(len(items), size=max_per_class, replace=False)
        out[label] = [items[int(index)] for index in choice]
    return out


def stack_xy(
    by_label: dict[str, list[np.ndarray]],
    charset: tuple[str, ...] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    index_of = (
        {char: i for i, char in enumerate(charset)}
        if charset is not None
        else LABEL_TO_INDEX
    )
    images: list[np.ndarray] = []
    labels: list[int] = []
    for label, items in by_label.items():
        index = index_of[label]
        for item in items:
            images.append(item)
            labels.append(index)
    if not images:
        raise ValueError("нет обучающих глифов")
    return np.stack(images, axis=0), np.asarray(labels, dtype=np.int64)


def class_weights(labels: np.ndarray, n_classes: int) -> np.ndarray:
    counts = np.bincount(labels, minlength=n_classes).astype(np.float32)
    counts = np.maximum(counts, 1.0)
    weights = counts.sum() / (n_classes * counts)
    return weights.astype(np.float32)


def _read_gray(path: Path) -> np.ndarray | None:
    import cv2

    encoded = np.fromfile(str(path), dtype=np.uint8)
    loaded = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
    return loaded


def group_emnist(
    images: Iterable[Any],
    targets: Iterable[int],
    keep: dict[int, str],
) -> dict[str, list[np.ndarray]]:
    grouped: dict[str, list[np.ndarray]] = defaultdict(list)
    for image, target in zip(images, targets):
        label = keep.get(int(target))
        if label is None:
            continue
        array = np.asarray(image, dtype=np.uint8)
        grouped[label].append(to_mnist_glyph(array, invert=True))
    return dict(grouped)


def weights_dir() -> Path:
    return project_root() / "output" / "ocr_glyph_cnn"


def make_glyph_cnn(torch: Any, n_classes: int):
    """Three conv blocks + 512-d head. Same net as training."""

    class GlyphCNN(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = torch.nn.Sequential(
                torch.nn.Conv2d(1, 64, 3, padding=1),
                torch.nn.BatchNorm2d(64),
                torch.nn.ReLU(inplace=True),
                torch.nn.Conv2d(64, 64, 3, padding=1),
                torch.nn.BatchNorm2d(64),
                torch.nn.ReLU(inplace=True),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(64, 128, 3, padding=1),
                torch.nn.BatchNorm2d(128),
                torch.nn.ReLU(inplace=True),
                torch.nn.Conv2d(128, 128, 3, padding=1),
                torch.nn.BatchNorm2d(128),
                torch.nn.ReLU(inplace=True),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(128, 256, 3, padding=1),
                torch.nn.BatchNorm2d(256),
                torch.nn.ReLU(inplace=True),
            )
            self.classifier = torch.nn.Sequential(
                torch.nn.Flatten(),
                torch.nn.Linear(256 * 7 * 7, 512),
                torch.nn.ReLU(inplace=True),
                torch.nn.Dropout(0.35),
                torch.nn.Linear(512, n_classes),
            )

        def forward(self, batch):
            return self.classifier(self.features(batch))

    return GlyphCNN()


def load_features_warm_start(model: Any, weights_path: Path, torch: Any) -> None:
    """Copy ``features.*`` from a previous checkpoint. Classifier is left random."""

    state = torch.load(weights_path, map_location="cpu", weights_only=True)
    feat = {
        key[len("features.") :]: value
        for key, value in state.items()
        if key.startswith("features.")
    }
    if not feat:
        raise RuntimeError(
            f"в {weights_path} нет слоёв features.*; warm-start невозможен"
        )
    missing, unexpected = model.features.load_state_dict(feat, strict=False)
    if missing:
        raise RuntimeError(
            f"warm-start: в checkpoint нет свёрточных ключей {list(missing)}"
        )
    del unexpected


def load_glyph_recognizer(directory: Path | None = None) -> tuple[Any, tuple[str, ...], Any]:
    """Load trained weights. CUDA if present, otherwise CPU."""

    import torch

    from chess_core.ocr.labels import charset_from_labels, load_labels_payload

    root = directory or weights_dir()
    if root.is_file():
        root = root.parent
    labels_path = root / "labels.json"
    weights_path = root / "glyph_cnn.pt"
    if not labels_path.is_file() or not weights_path.is_file():
        raise FileNotFoundError(
            f"нет весов CNN в {root}. Сначала: python -m chess_core.tools.train_glyph_cnn"
        )
    payload = load_labels_payload(labels_path)
    charset = charset_from_labels(payload)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = make_glyph_cnn(torch, len(charset))
    state = torch.load(weights_path, map_location=device, weights_only=True)
    try:
        model.load_state_dict(state)
    except RuntimeError as exc:
        raise RuntimeError(
            f"веса {weights_path} не стыкуются с {len(charset)} классами из {labels_path}: {exc}"
        ) from exc
    model.to(device)
    model.eval()
    return model, charset, device


def fold_read_char(char: str) -> str:
    return READ_EQUIV.get(char, char)


def merge_equivalent_probs(probs, charset: tuple[str, ...]):
    return probs


def predict_mnist_tiles(
    tiles: list[np.ndarray],
    model: Any,
    charset: tuple[str, ...],
    device: Any,
) -> list[tuple[str, float, tuple[tuple[str, float], ...]]]:
    """Classify MNIST-sized tiles into role ids (or legacy letter classes)."""

    import torch

    if not tiles:
        return []
    batch = np.stack(tiles, axis=0).astype(np.float32) / 255.0
    tensor = torch.from_numpy(batch).unsqueeze(1).to(device)
    with torch.no_grad():
        logits = model(tensor)
        probs = torch.softmax(logits, dim=1)
        top = torch.topk(probs, k=min(5, len(charset)), dim=1)
    out: list[tuple[str, float, tuple[tuple[str, float], ...]]] = []
    role_mode = charset and charset[0] in ROLE_BY_ID
    for row in range(len(tiles)):
        indices = top.indices[row].tolist()
        scores = top.values[row].tolist()
        raw = tuple(
            (charset[int(index)], float(score))
            for index, score in zip(indices, scores)
        )
        alts = tuple(item for item in raw if item[1] > 0) or raw[:1]
        char, score = alts[0]
        if not role_mode and score < MIN_GLYPH_SCORE:
            char = GARBAGE
        out.append((char, score, alts))
    return out


def save_labeled_montage(
    tiles: list[np.ndarray],
    captions: list[str],
    path: Path,
    *,
    cols: int = 12,
) -> Path | None:
    import cv2

    if not tiles:
        return None
    cell = 56
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
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", sheet)[1].tofile(str(path))
    return path
