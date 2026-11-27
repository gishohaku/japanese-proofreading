#!/usr/bin/env python3
"""スキルを .skill ファイル（zip）にまとめる。node_modules などは含めない。

zip コマンドのない環境（Windows など）でも動くよう、標準ライブラリの zipfile を使う。
"""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
NAME = "japanese-proofreading"
OUT = ROOT / "dist" / f"{NAME}.skill"
EXCLUDE_DIRS = {"node_modules", "__pycache__"}
EXCLUDE_FILES = {".DS_Store", ".write-test"}


def included(path: Path) -> bool:
    rel = path.relative_to(SKILLS)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return False
    return path.name not in EXCLUDE_FILES and path.suffix != ".pyc"


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    OUT.unlink(missing_ok=True)
    files = sorted(p for p in (SKILLS / NAME).rglob("*") if p.is_file() and included(p))
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            # zip 内のパスは OS によらず / 区切りにする
            zf.write(p, p.relative_to(SKILLS).as_posix())
    print(f"{OUT.relative_to(ROOT).as_posix()} を作成しました（{len(files)} ファイル）。")


if __name__ == "__main__":
    main()
