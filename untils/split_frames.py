import argparse
from pathlib import Path

from PIL import Image


def extract_frames(input_path: Path, output_dir: Path, prefix: str, start_index: int, max_frames: int | None):
    output_dir.mkdir(parents=True, exist_ok=True)

    im = Image.open(input_path)
    n_frames = getattr(im, "n_frames", 1)
    is_animated = bool(getattr(im, "is_animated", False)) and n_frames > 1

    if not is_animated:
        rgba = im.convert("RGBA")
        out_path = output_dir / f"{prefix}_{start_index}.png"
        rgba.save(out_path, format="PNG")
        return 1

    canvas = Image.new("RGBA", im.size, (0, 0, 0, 0))
    written = 0
    palette = im.getpalette()

    for i in range(n_frames):
        if max_frames is not None and written >= max_frames:
            break

        im.seek(i)
        if im.mode == "P" and im.getpalette() is None and palette is not None:
            im.putpalette(palette)

        disposal = getattr(im, "disposal_method", 0) or 0
        dispose_extent = getattr(im, "dispose_extent", None)
        tile_extent = im.tile[0][1] if im.tile else (0, 0, im.size[0], im.size[1])

        restore_before = None
        if disposal == 3:
            restore_before = canvas.copy()

        frame_rgba = im.convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        if tile_extent and tile_extent != (0, 0, im.size[0], im.size[1]):
            region = frame_rgba.crop(tile_extent)
            overlay.paste(region, (tile_extent[0], tile_extent[1]))
        else:
            overlay.paste(frame_rgba, (0, 0))
        canvas = Image.alpha_composite(canvas, overlay)

        out_index = start_index + written
        out_path = output_dir / f"{prefix}_{out_index}.png"
        canvas.save(out_path, format="PNG")
        written += 1

        if disposal == 2 and dispose_extent:
            x0, y0, x1, y1 = dispose_extent
            if x1 > x0 and y1 > y0:
                clear = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
                canvas.paste(clear, (x0, y0))
        elif disposal == 3 and restore_before is not None:
            canvas = restore_before

    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="输入动图文件或目录路径（GIF/APNG/WEBP 等）")
    parser.add_argument("--out-dir", default=None, help="输出目录（输入为文件：默认 <输入文件名>_frames；输入为目录：默认输出到该目录下）")
    parser.add_argument("--prefix", default=None, help="输出文件前缀（仅输入为文件时生效，默认：输入文件名）")
    parser.add_argument("--start-index", type=int, default=1, help="帧编号起始值（默认 1）")
    parser.add_argument("--max-frames", type=int, default=None, help="最多导出多少帧（默认不限）")
    parser.add_argument("--include-static", action="store_true", help="目录模式下也导出静态图（默认跳过）")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"找不到输入文件：{input_path}")

    if input_path.is_dir():
        output_root = Path(args.out_dir).expanduser().resolve() if args.out_dir else input_path
        total = 0
        converted = 0
        for p in sorted(input_path.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".png", ".gif", ".webp"}:
                continue
            try:
                im = Image.open(p)
            except Exception:
                continue
            n_frames = getattr(im, "n_frames", 1)
            is_animated = bool(getattr(im, "is_animated", False)) and n_frames > 1
            if not is_animated and not args.include_static:
                continue
            out_dir = output_root / p.stem
            written = extract_frames(
                input_path=p,
                output_dir=out_dir,
                prefix=p.stem,
                start_index=args.start_index,
                max_frames=args.max_frames,
            )
            total += written
            converted += 1
            print(f"{p.name} -> {out_dir} ({written} 帧)")
        print(f"已处理 {converted} 个文件，共导出 {total} 帧")
        return

    prefix = args.prefix or input_path.stem
    output_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else input_path.with_name(f"{input_path.stem}_frames")
    written = extract_frames(
        input_path=input_path,
        output_dir=output_dir,
        prefix=prefix,
        start_index=args.start_index,
        max_frames=args.max_frames,
    )

    print(f"已导出 {written} 帧到：{output_dir}")


if __name__ == "__main__":
    main()
