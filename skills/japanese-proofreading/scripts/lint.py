#!/usr/bin/env python3
"""textlint を実行し、校正スキルが読みやすい形に要約する。

使い方:
    python scripts/lint.py <file> [<file> ...] [--json]

- 初回は `npm ci` を実行して依存関係を入れる（ネットワークが必要）。
  スキルのディレクトリが書き込み禁止の場合（claude.ai など）は、設定と辞書を
  キャッシュディレクトリ（既定は ~/.cache/japanese-proofreading/textlint、
  環境変数 JAPANESE_PROOFREADING_CACHE で変更可）にコピーして、そこで実行する。
- 出力は「該当する文の文字列」を必ず含める。textlint の行番号はルールによって
  ずれることがあるため、スキルは文字列で照合する。
- 終了コード：0 = 実行できた（指摘の有無は問わない）、1 = 引数の誤り（ファイルが
  ない、対応していない形式）、2 = textlint を実行できない環境（Node.js がない、
  依存関係を入れられない）。スキルは 2 の場合だけ、ルール集だけで校正を続ける。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = SKILL_DIR / "textlint"
CACHE_DIR = Path(os.environ.get(
    "JAPANESE_PROOFREADING_CACHE",
    Path.home() / ".cache" / "japanese-proofreading")) / "textlint"
SYNC_FILES = [".textlintrc.json", "package.json", "package-lock.json"]


def is_writable(directory: Path) -> bool:
    """読み取り専用でマウントされた場合も判定できるよう、実際に書き込んで確かめる。"""
    if os.environ.get("JAPANESE_PROOFREADING_FORCE_CACHE"):
        return False
    try:
        probe = directory / ".write-test"
        probe.write_text("")
        probe.unlink()
        return True
    except OSError:
        return False


def prepare_workdir() -> Path:
    """textlint を実行するディレクトリを返す。書き込めなければキャッシュに複製する。"""
    if is_writable(SOURCE_DIR):
        return SOURCE_DIR
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    lock_changed = False
    for name in SYNC_FILES:
        src, dst = SOURCE_DIR / name, CACHE_DIR / name
        if not dst.exists() or src.read_bytes() != dst.read_bytes():
            shutil.copyfile(src, dst)
            lock_changed |= name in ("package.json", "package-lock.json")
    if (CACHE_DIR / "prh").exists():
        shutil.rmtree(CACHE_DIR / "prh")
    shutil.copytree(SOURCE_DIR / "prh", CACHE_DIR / "prh")
    if lock_changed and (CACHE_DIR / "node_modules").exists():
        shutil.rmtree(CACHE_DIR / "node_modules")
    return CACHE_DIR


TEXTLINT_DIR = SOURCE_DIR  # main() で prepare_workdir() の結果に置き換える

# textlint のプラグインが対応している拡張子（.textlintrc.json の plugins と合わせる）
SUPPORTED_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd", ".txt", ".text", ".re"}
INSTALL_TIMEOUT_SEC = 600

# textlint のルールID → 校正ルール集のルールID
RULE_MAP = {
    "sentence-length": "BUN-06",
    "max-comma": "BUN-07",
    "max-ten": "BUN-07",
    "max-kanji-continuous-len": "MOJI-08",
    "arabic-kanji-numbers": "MOJI-03",
    "no-mix-dearu-desumasu": "TOITSU-03",
    "ja-no-mixed-period": "MOJI-01",
    "no-double-negative-ja": "BUN-08",
    "no-dropping-the-ra": "GOI-03",
    "no-doubled-conjunctive-particle-ga": "JOSHI-01",
    "no-doubled-conjunction": "JOSHI-09",
    "no-doubled-joshi": "KAKU-02",
    "no-nfd": "MOJI-07",
    "no-invalid-control-character": "MOJI-07",
    "no-zero-width-spaces": "MOJI-07",
    "no-hankaku-kana": "MOJI-02",
    "ja-no-weak-phrase": "GOI-07",
    "ja-no-successive-word": "JOSHI-10",
    "ja-no-abusage": "GOI-02",
    "ja-no-redundant-expression": "GOI-09",
    "ja-unnatural-alphabet": "MOJI-02",
    "no-unmatched-pair": "MOJI-06",
    "no-synonyms": "TOITSU-01",
    "1.1.1.本文": "TOITSU-03",
    "1.2.1.句点(。)と読点(、)": "MOJI-01",
    "4.1.1.句点(。)": "MOJI-01",
    "1.2.2.ピリオド(.)とカンマ(,)": "MOJI-01",
    "2.1.8.算用数字": "MOJI-02",
    "2.1.9.アルファベット": "MOJI-02",
    "2.2.2.算用数字と漢数字の使い分け": "MOJI-03",
    "2.2.3.一部の助数詞の表記": "MOJI-04",
    "3.1.2.全角文字どうし": "MOJI-05",
    "3.3.かっこ類と隣接する文字の間のスペースの有無": "MOJI-05",
    "4.2.2.疑問符(？)": "MOJI-05",
    "4.2.9.ダッシュ(－)": "MOJI-06",
    "4.3.1.丸かっこ（）": "MOJI-06",
    "4.3.2.大かっこ［］": "MOJI-06",
}



def ensure_deps() -> bool:
    if (TEXTLINT_DIR / "node_modules" / ".bin" / "textlint").exists():
        return True
    if shutil.which("npm") is None:
        print("textlint を実行できません: npm が見つかりません。", file=sys.stderr)
        return False
    cmd = ["npm", "ci", "--no-audit", "--no-fund", "--loglevel=error"]
    print("textlint の依存関係をインストールしています（初回のみ、約30MB）…", file=sys.stderr)
    try:
        result = subprocess.run(cmd, cwd=TEXTLINT_DIR, capture_output=True, text=True,
                                timeout=INSTALL_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        print("textlint の依存関係のインストールが時間切れになりました。", file=sys.stderr)
        return False
    if result.returncode != 0:
        print("textlint の依存関係を入れられませんでした。", file=sys.stderr)
        print(result.stderr.strip()[-2000:], file=sys.stderr)
        return False
    return True


def run_textlint(files: list[Path]) -> list[dict]:
    binary = TEXTLINT_DIR / "node_modules" / ".bin" / "textlint"
    cmd = [str(binary), "--config", str(TEXTLINT_DIR / ".textlintrc.json"),
           "--format", "json", *[str(f) for f in files]]
    # 指摘があると終了コード 1 になるため、終了コードではなく出力で判定する
    result = subprocess.run(cmd, cwd=TEXTLINT_DIR, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print("textlint の出力を読めませんでした。", file=sys.stderr)
        print((result.stderr or result.stdout).strip()[-2000:], file=sys.stderr)
        sys.exit(2)


def short_rule(rule_id: str) -> str:
    # "ja-technical-writing/max-ten" → "max-ten"、"prh" はそのまま
    return rule_id.split("/", 1)[1] if "/" in rule_id else rule_id


def sentence_at(text: str, index: int) -> str:
    """index を含む文を返す。かっこの中の句点では文を区切らない。"""
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index)
    line = text[line_start: len(text) if line_end < 0 else line_end]
    pos = index - line_start
    start, depth = 0, 0
    for i, ch in enumerate(line):
        if ch in "「『（(":
            depth += 1
        elif ch in "」』）)" and depth > 0:
            depth -= 1
        elif ch in "。！？!?" and depth == 0:
            if i >= pos:
                return line[start:i + 1].strip()
            start = i + 1
    return line[start:].strip()


def map_rule(rule_id: str, message: str) -> str:
    if rule_id == "prh":
        # house.yml の prh メッセージ先頭にルールIDを書いている
        m = re.search(r"\b(OKURI|HIRAKU|GOI|KAKU|JOSHI|BUN|MOJI)-\d+", message)
        if m:
            return m.group(0)
        if "重言" in message:
            return "GOI-04"
        if "誤字" in message:
            return "GOI-10"
        return "GOI-01"
    return RULE_MAP.get(short_rule(rule_id), "-")


def relocate_doubled_ga(text: str, used: set[int]) -> tuple[int, str] | None:
    """no-doubled-conjunctive-particle-ga は報告位置がずれることがあるため、
    「が、」を2回以上含む文を本文から探し直す。"""
    for m in re.finditer(r"[^。！？!?\n]+[。！？!?]?", text):
        if m.start() in used:
            continue
        if len(re.findall(r"が、", m.group(0))) >= 2:
            used.add(m.start())
            return m.start(), m.group(0).strip()
    return None


def short_message(it: dict) -> str:
    """指摘の文言を短くする（スキルが読むトークンを減らすため）。"""
    msg, rule = it["message"], short_rule(it["textlint_rule"])
    if it["textlint_rule"] == "prh":
        m = re.match(r"^(.*? => \S+)", msg)
        return m.group(1) if m else msg
    if rule == "sentence-length":
        m = re.search(r"length\((\d+)\) exceeds the maximum sentence length of (\d+)", msg)
        if m:
            return f"文が長い：{m.group(1)}字（上限{m.group(2)}字）（{rule}）"
    if rule == "max-ten":
        return f"読点が4つ以上（{rule}）"
    if rule == "max-kanji-continuous-len":
        m = re.search(r": (\S+)", msg)
        return f"漢字の連続：{m.group(1) if m else ''}（{rule}）"
    if rule == "no-mix-dearu-desumasu":
        m = re.search(r"=> (.*?)(Total:|$)", msg)
        if m:
            msg = m.group(1).strip()
    msg = re.split(r"\s*解説:", msg)[0].strip()  # 解説の URL を省く
    msg = re.sub(r"^【dict\d+】\s*", "", msg)
    return f"{msg}（{rule}）"


def net_length(sentence: str) -> int:
    """リンクの URL、インラインコード、かっこ内の補足を除いた文の長さ。"""
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", sentence)
    s = re.sub(r"`[^`]*`", "X", s)
    s = re.sub(r"（[^（）]*）|\([^()]*\)", "", s)
    return len(s)


SKIPPED: dict[str, int] = {}


def summarize(results: list[dict]) -> list[dict]:
    items = []
    for file_result in results:
        path = Path(file_result["filePath"])
        text = path.read_text(encoding="utf-8", errors="replace")
        used_ga: set[int] = set()
        for msg in file_result["messages"]:
            index = msg.get("range", [msg.get("index", 0)])[0]
            message = msg["message"].replace("\n", " ")
            sentence = sentence_at(text, index)
            line = msg.get("line")
            if short_rule(msg["ruleId"]) == "no-doubled-conjunctive-particle-ga" \
                    and len(re.findall(r"が、", sentence)) < 2:
                found = relocate_doubled_ga(text, used_ga)
                if found:
                    line = text.count("\n", 0, found[0]) + 1
                    sentence = found[1]
                    message += "（位置を再推定）"
            if short_rule(msg["ruleId"]) == "sentence-length":
                m = re.search(r"maximum sentence length of (\d+)", message)
                if m and net_length(sentence) <= int(m.group(1)):
                    # コードやリンク、かっこ内の補足で長くなっているだけの文は除く
                    SKIPPED["sentence-length"] = SKIPPED.get("sentence-length", 0) + 1
                    continue
            items.append({
                "file": str(path),
                "line": line,
                "column": msg.get("column"),
                "rule": map_rule(msg["ruleId"], message),
                "textlint_rule": msg["ruleId"],
                "fixable": "fix" in msg,
                "message": message,
                "sentence": sentence,
            })
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", help="JSON で出力する")
    parser.add_argument("--full", action="store_true",
                        help="該当文を省略せずに表示する（既定は先頭80字、リンクの URL は省略）")
    args = parser.parse_args()

    # macOS の zip に含まれる __MACOSX/ や ._ ファイルは原稿ではないので除く
    files = [f.resolve() for f in args.files
             if not f.name.startswith("._") and "__MACOSX" not in f.parts]
    if not files:
        print("対象の原稿がありません。", file=sys.stderr)
        return 1
    for f in files:
        if not f.is_file():
            print(f"ファイルが見つかりません: {f}", file=sys.stderr)
            return 1
        if f.suffix.lower() not in SUPPORTED_EXTENSIONS:
            print(f"対応していない形式です: {f.name}（対応: Markdown、テキスト、Re:VIEW。"
                  "ほかの形式はテキストを抽出して .md で保存してから渡す）", file=sys.stderr)
            return 1

    global TEXTLINT_DIR
    try:
        TEXTLINT_DIR = prepare_workdir()
    except OSError as e:
        print(f"textlint の作業ディレクトリを用意できません: {e}", file=sys.stderr)
        return 2
    if not ensure_deps():
        return 2

    items = summarize(run_textlint(files))

    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    if not items:
        print("textlint の指摘はありません。")
        if SKIPPED.get("sentence-length"):
            print(f"（コード・リンク・かっこ内の補足を除くと上限以下になる長文 "
                  f"{SKIPPED['sentence-length']} 件は省略）")
        return 0
    # 同じ文への指摘をまとめ、文は1回だけ表示する（出力を短くするため）
    groups: dict[tuple[str, str], list[dict]] = {}
    for it in items:
        groups.setdefault((it["file"], it["sentence"]), []).append(it)
    counts: dict[str, int] = {}
    for it in items:
        counts[it["rule"]] = counts.get(it["rule"], 0) + 1
    print(f"textlint の指摘: {len(items)} 件 / {len(groups)} 文"
          "（行番号は目安。文の文字列で照合すること。[fix] は自動修正可）")
    print("ルール別: " + "、".join(f"{r} {n}" for r, n in
                                 sorted(counts.items(), key=lambda x: -x[1])))
    if SKIPPED.get("sentence-length"):
        print(f"（コード・リンク・かっこ内の補足を除くと上限以下になる長文 "
              f"{SKIPPED['sentence-length']} 件は省略）")
    current_file = None
    for (file, sentence), its in groups.items():
        if file != current_file:
            current_file = file
            print(f"\n## {Path(file).name}")
        shown = re.sub(r"\]\([^)]*\)", "]", sentence)  # 表示ではリンクの URL を省く
        if not args.full and len(shown) > 80:
            shown = shown[:80] + "…"
        print(f"\n{its[0]['line']}: {shown}")
        for it in its:
            mark = " [fix]" if it["fixable"] else ""
            print(f"  - {it['rule']} {short_message(it)}{mark}")
    return 0


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # head などに渡しても例外を出さない
    sys.exit(main())
