from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from image_layout_utils import prepare_logo_image, prepare_site_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a logo or right-side visual for buyer-board layout placement.")
    parser.add_argument("--input", required=True, help="Source image path")
    parser.add_argument("--kind", required=True, choices=["logo", "site"], help="Asset kind")
    parser.add_argument("--target-width", type=int, help="Target box width for site visuals")
    parser.add_argument("--target-height", type=int, help="Target box height for site visuals")
    parser.add_argument("--output-dir", help="Optional output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else Path(tempfile.mkdtemp(prefix="buyer-board-prep-"))
    output_dir.mkdir(parents=True, exist_ok=True)
    source = Path(args.input)

    if args.kind == "logo":
        prepared = prepare_logo_image(source, output_dir, args.target_width, args.target_height)
    else:
        if not args.target_width or not args.target_height:
            raise SystemExit("--target-width and --target-height are required for site assets.")
        prepared = prepare_site_image(source, output_dir, args.target_width, args.target_height)

    print(prepared.output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
