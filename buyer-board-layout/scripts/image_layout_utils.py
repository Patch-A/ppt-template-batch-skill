from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat


TARGET_RENDER_WIDTH = 1600
MIN_RETENTION_FOR_HARD_CROP = 0.6
MAX_UPSCALE_FOR_HARD_CROP = 2.4
FOREGROUND_PADDING_RATIO = 0.06


@dataclass
class PreparedAsset:
    output_path: Path
    mode: str
    retention: float
    upscale: float
    notes: str


def normalize_image(path: Path, temp_dir: Path) -> Path:
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"}:
        return path

    if suffix == ".svg":
        try:
            import cairosvg
        except Exception as exc:
            raise RuntimeError(
                "SVG conversion requires cairosvg with a working cairo runtime. "
                f"Install cairo or replace the SVG logo with PNG/JPG. Source: {path}"
            ) from exc

        out = temp_dir / f"{path.stem}.png"
        cairosvg.svg2png(url=str(path), write_to=str(out))
        return out

    if suffix == ".webp":
        out = temp_dir / f"{path.stem}.png"
        Image.open(path).save(out, "PNG")
        return out

    raise ValueError(f"Unsupported image format: {path}")


def trim_uniform_border(image: Image.Image, tolerance: int = 12) -> Image.Image:
    rgba = image.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, rgba.getpixel((0, 0)))
    diff = ImageChops.difference(rgba, bg)
    diff = ImageChops.add(diff, diff, 2.0, -tolerance)
    bbox = diff.getbbox()
    return rgba.crop(bbox) if bbox else rgba


def fit_size(src_width: int, src_height: int, box_width: int, box_height: int) -> tuple[int, int]:
    ratio = min(box_width / src_width, box_height / src_height)
    return max(1, int(src_width * ratio)), max(1, int(src_height * ratio))


def white_ratio(image: Image.Image) -> float:
    probe = image.convert("RGB").resize((64, 64))
    pixels = list(probe.getdata())
    total = len(pixels)
    if not total:
        return 1.0
    white_count = sum(1 for r, g, b in pixels if r >= 240 and g >= 240 and b >= 240)
    return white_count / total


def crop_score(image: Image.Image, crop_box: tuple[int, int, int, int]) -> float:
    crop = image.crop(crop_box).convert("RGB")
    edges = crop.filter(ImageFilter.FIND_EDGES).convert("L")
    edge_stat = ImageStat.Stat(edges)
    contrast_stat = ImageStat.Stat(crop.convert("L"))
    edge_score = edge_stat.mean[0]
    contrast_score = contrast_stat.stddev[0]
    blank_penalty = white_ratio(crop) * 30.0
    return (edge_score * 1.8) + contrast_score - blank_penalty


def smart_crop_box(image: Image.Image, target_ratio: float) -> tuple[int, int, int, int]:
    source_ratio = image.width / image.height
    if abs(source_ratio - target_ratio) < 0.01:
        return (0, 0, image.width, image.height)

    if source_ratio > target_ratio:
        crop_width = max(1, int(image.height * target_ratio))
        max_offset = max(0, image.width - crop_width)
        offsets = sorted(
            {
                0,
                max_offset,
                max_offset // 2,
                max_offset // 4,
                (max_offset * 3) // 4,
                max_offset // 6,
                (max_offset * 5) // 6,
            }
        )
        best = max(offsets, key=lambda offset: crop_score(image, (offset, 0, offset + crop_width, image.height)))
        return (best, 0, best + crop_width, image.height)

    crop_height = max(1, int(image.width / target_ratio))
    max_offset = max(0, image.height - crop_height)
    offsets = sorted(
        {
            0,
            max_offset,
            max_offset // 2,
            max_offset // 4,
            (max_offset * 3) // 4,
            max_offset // 6,
            (max_offset * 5) // 6,
        }
    )
    best = max(offsets, key=lambda offset: crop_score(image, (0, offset, image.width, offset + crop_height)))
    return (0, best, image.width, best + crop_height)


def render_size_for_ratio(target_ratio: float) -> tuple[int, int]:
    width = TARGET_RENDER_WIDTH
    height = max(1, int(round(width / target_ratio)))
    return width, height


def prepare_site_image(image_path: Path, temp_dir: Path, target_width: int, target_height: int) -> PreparedAsset:
    normalized = normalize_image(image_path, temp_dir)
    image = Image.open(normalized).convert("RGB")
    trimmed = trim_uniform_border(image, tolerance=10).convert("RGB")

    target_ratio = target_width / target_height
    crop_box = smart_crop_box(trimmed, target_ratio)
    crop_width = crop_box[2] - crop_box[0]
    crop_height = crop_box[3] - crop_box[1]
    retention = (crop_width * crop_height) / (trimmed.width * trimmed.height)

    render_width, render_height = render_size_for_ratio(target_ratio)
    upscale = max(render_width / crop_width, render_height / crop_height)

    out = temp_dir / f"{image_path.stem}-site-prepared.png"
    if retention >= MIN_RETENTION_FOR_HARD_CROP and upscale <= MAX_UPSCALE_FOR_HARD_CROP:
        cropped = trimmed.crop(crop_box).resize((render_width, render_height), Image.Resampling.LANCZOS)
        cropped.save(out, "PNG")
        return PreparedAsset(
            output_path=out,
            mode="smart_crop_fill",
            retention=round(retention, 3),
            upscale=round(upscale, 3),
            notes="content-aware crop",
        )

    background = trimmed.crop(crop_box).resize((render_width, render_height), Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=18))
    background = ImageEnhanceSafe.apply_dim(background, factor=0.82)

    canvas = background
    pad_x = int(render_width * FOREGROUND_PADDING_RATIO)
    pad_y = int(render_height * FOREGROUND_PADDING_RATIO)
    fg_width, fg_height = fit_size(trimmed.width, trimmed.height, render_width - (pad_x * 2), render_height - (pad_y * 2))
    foreground = trimmed.resize((fg_width, fg_height), Image.Resampling.LANCZOS)
    fg_left = (render_width - fg_width) // 2
    fg_top = (render_height - fg_height) // 2
    canvas.paste(foreground, (fg_left, fg_top), foreground.convert("RGBA"))
    canvas.save(out, "PNG")
    return PreparedAsset(
        output_path=out,
        mode="blurred_backdrop_fit",
        retention=round(retention, 3),
        upscale=round(upscale, 3),
        notes="extreme ratio fallback with preserved full subject",
    )


def prepare_logo_image(
    image_path: Path,
    temp_dir: Path,
    target_width: int | None = None,
    target_height: int | None = None,
) -> PreparedAsset:
    normalized = normalize_image(image_path, temp_dir)
    image = Image.open(normalized)
    trimmed = trim_uniform_border(image)
    out = temp_dir / f"{image_path.stem}-logo-prepared.png"

    if target_width and target_height:
        target_ratio = target_width / target_height
        canvas_width = TARGET_RENDER_WIDTH
        canvas_height = max(1, int(round(canvas_width / target_ratio)))
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 0))
        source = trimmed.convert("RGBA")
        fitted_width, fitted_height = fit_size(source.width, source.height, canvas_width, int(canvas_height * 0.9))
        fitted = source.resize((fitted_width, fitted_height), Image.Resampling.LANCZOS)
        canvas.paste(fitted, (0, (canvas_height - fitted_height) // 2), fitted)
        canvas.save(out, "PNG")
        return PreparedAsset(
            output_path=out,
            mode="logo_canvas_fit",
            retention=1.0,
            upscale=round(max(fitted_width / source.width, fitted_height / source.height), 3),
            notes="logo fitted into target slot aspect without distortion",
        )

    trimmed.save(out, "PNG")
    return PreparedAsset(
        output_path=out,
        mode="trimmed_logo",
        retention=1.0,
        upscale=1.0,
        notes="logo border trimmed",
    )


class ImageEnhanceSafe:
    @staticmethod
    def apply_dim(image: Image.Image, factor: float) -> Image.Image:
        factor = max(0.0, min(factor, 1.0))
        overlay = Image.new("RGB", image.size, (0, 0, 0))
        return Image.blend(overlay, image, factor)
