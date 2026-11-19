#!/usr/bin/env python3
"""回帰テスト：tests/regression.md に埋め込んだ誤りを、スクリプトが検出できるか確かめる。

detected_by が textlint の項目は lint.py が、consistency の項目は consistency.py が
検出しなければ失敗とする。skill の項目は文脈の判断が必要なので、件数だけ表示する。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "japanese-proofreading" / "scripts"
SAMPLE = ROOT / "tests" / "regression.md"

lint = json.loads(subprocess.run(
    [sys.executable, str(SCRIPTS / "lint.py"), str(SAMPLE), "--json", "--full"],
    capture_output=True, text=True, check=True).stdout)
cons = subprocess.run(
    [sys.executable, str(SCRIPTS / "consistency.py"), str(SAMPLE)],
    capture_output=True, text=True, check=True).stdout

failed = 0
expected = json.loads((ROOT / "tests" / "expected.json").read_text(encoding="utf-8"))
for case in expected:
    if case["detected_by"] == "textlint":
        ok = any(it["rule"] == case["rule"] and case["sentence"][:6] in it["sentence"] for it in lint)
    elif case["detected_by"] == "consistency":
        # consistency.py の出力に、期待する集計の行（needle）が含まれるかを見る
        ok = case["needle"] in cons
    else:
        print(f"  skill    {case['rule']:10} {case['sentence']}")
        continue
    print(f"{'  ok  ' if ok else '  NG  '} {case['detected_by']:8} {case['rule']:10} {case['sentence']}")
    failed += not ok

print(f"\n失敗: {failed} 件")
sys.exit(1 if failed else 0)
