#!/usr/bin/env python3
"""文書全体の表記ゆれ・文体のゆれを集計する。

使い方:
    python scripts/consistency.py <file> [<file> ...] [--json]

textlint は文や語の単位でチェックするため、「文書全体で多数派はどちらか」
「同じ対象が何通りの表記で出てくるか」は苦手。このスクリプトはそれを集計し、
スキルが表記方針（references/rules/toitsu.md の判定の手順）を決め、TOITSU 系の指摘を
出すための材料にする。判定はしない。候補と件数を出すだけ。

複数ファイルを渡すと、まとめて1つの文書として集計する（書籍の全章など）。
"""

from __future__ import annotations

import argparse
import json
import re
import signal
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 本文の抽出（コード・マークアップを除く）
# ---------------------------------------------------------------------------

FENCE = re.compile(r"^(```|~~~)")
REVIEW_BLOCK_START = re.compile(r"^//[a-z]+(\[.*?\])*\{\s*$")
REVIEW_BLOCK_END = re.compile(r"^//\}\s*$")
INLINE_CODE_MD = re.compile(r"`[^`]*`")
# Re:VIEW のインライン命令。装飾（太字など）とルビは中の本文を残し、それ以外（コード、参照など）は除く
INLINE_REVIEW_TEXT = re.compile(r"@<(?:b|i|em|strong|u|ami|bou|tti|ttb|ins|del|tcy)>\{([^}]*)\}")
INLINE_REVIEW_RUBY = re.compile(r"@<ruby>\{([^,}]*),[^}]*\}")
INLINE_REVIEW = re.compile(r"@<[a-z]+>\{[^}]*\}")
LIST_ITEM = re.compile(r"^([-*+]\s|\d+[.)]\s|: )")
HTML_TAG = re.compile(r"<[^>]+>")
URL = re.compile(r"https?://\S+")
MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")  # [text](url) → text


def extract_lines(text: str) -> list[tuple[int, str, str]]:
    """(行番号, 種類, 本文) のリストを返す。種類は body / heading / list / quote / table。"""
    out = []
    in_code = False
    in_list = False
    in_front = text.startswith("---\n")  # YAML フロントマターは対象外
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if in_front:
            if no > 1 and line == "---":
                in_front = False
            continue
        if FENCE.match(line.strip()):
            in_code = not in_code
            continue
        if REVIEW_BLOCK_START.match(line):
            in_code = True
            continue
        if in_code and REVIEW_BLOCK_END.match(line):
            in_code = False
            continue
        if in_code or not line.strip():
            continue
        stripped = line.strip()
        is_list_item = bool(LIST_ITEM.match(stripped))
        indented = line.startswith("    ") or line.startswith("\t")
        if indented and not (is_list_item or in_list):
            continue  # インデントによるコードブロック（箇条書きの入れ子・項目の続きは本文として扱う）
        if is_list_item:
            in_list = True
        elif not indented:
            in_list = False
        if line.startswith("#@") or line.startswith("//"):
            continue  # Re:VIEW のコメント・命令
        kind = "body"
        if re.match(r"^(#{1,6}\s|=+(\[.*?\])?\s)", stripped):
            kind = "heading"
        elif is_list_item or indented:
            kind = "list"
        elif stripped.startswith(">"):
            kind = "quote"
        elif stripped.startswith("|"):
            kind = "table"
        body = INLINE_CODE_MD.sub(" ", stripped)
        body = INLINE_REVIEW_RUBY.sub(r"\1", body)
        body = INLINE_REVIEW_TEXT.sub(r"\1", body)
        body = INLINE_REVIEW.sub(" ", body)
        body = MD_LINK.sub(r"\1", body)
        body = URL.sub(" ", body)
        body = HTML_TAG.sub("", body)
        out.append((no, kind, body))
    return out


# ---------------------------------------------------------------------------
# 文末（敬体・常体）
# ---------------------------------------------------------------------------

KEITAI = re.compile(
    r"(です|ます|でした|ました|ません|ませんでした|でしょう|ましょう|ください|下さい)"
    r"(か|ね|よ)?[。！？!?）」』]*$")
JOTAI = re.compile(
    r"(だ|である|であった|だった|ではない|でない|ない|なかった|た|る|う|い|だろう|か)"
    r"[。！？!?）」』]*$")
OPEN_BRACKETS = "「『（(［["
CLOSE_BRACKETS = "」』）)］]"


def split_sentences(text: str) -> list[str]:
    """句点で文に分ける。かっこの中の句点（「〜です。」など）では分けない。"""
    out, buf, depth = [], [], 0
    for ch in text:
        buf.append(ch)
        if ch in OPEN_BRACKETS:
            depth += 1
        elif ch in CLOSE_BRACKETS and depth > 0:
            depth -= 1
        elif ch in "。！？!?" and depth == 0:
            out.append("".join(buf))
            buf = []
    if buf:
        out.append("".join(buf))
    return out


def sentence_endings(lines):
    keitai, jotai, other = [], [], []
    for no, kind, body in lines:
        if kind in ("heading", "table", "quote"):
            continue
        for s in split_sentences(body):
            s = s.strip()
            if not s or not re.search(r"[。！？!?]$", s):
                continue  # 句点で終わらない（体言止めの箇条書きなど）は数えない
            s_core = re.sub(r"[（(][^）)]*[）)]$", "", s.rstrip("。！？!?")) + "。"
            if KEITAI.search(s_core):
                keitai.append((no, kind, s))
            elif JOTAI.search(s_core):
                jotai.append((no, kind, s))
            else:
                other.append((no, kind, s))
    return keitai, jotai, other


# ---------------------------------------------------------------------------
# 表記ゆれ
# ---------------------------------------------------------------------------

KATAKANA_WORD = re.compile(r"[ァ-ヴー]{3,}")
ALPHA_WORD = re.compile(r"(?<![A-Za-z0-9_./])[A-Za-z][A-Za-z0-9.+#-]*[A-Za-z0-9+#](?![A-Za-z0-9_/])")


def normalize_katakana(w: str) -> str:
    w = w.replace("・", "")
    w = re.sub(r"ー+$", "", w)          # 語尾の長音
    w = w.replace("ヴァ", "バ").replace("ヴィ", "ビ").replace("ヴェ", "ベ")
    w = w.replace("ヴォ", "ボ").replace("ヴ", "ブ")
    w = w.replace("ウィ", "ウイ").replace("ウェ", "ウエ").replace("ウォ", "ウオ")
    w = w.replace("ティ", "チ").replace("ディ", "ジ")
    w = re.sub(r"ー", "", w)            # 語中の長音（インターフェース／インタフェース）
    w = w.replace("イ", "エ") if w.endswith("フェイス") else w
    return w


# 意味が同じで表記が異なる語の組（文字の正規化では拾えないもの）。
# 左端を「既定で推奨する表記」とする。
VARIANT_SETS: list[tuple[str, list[str]]] = [
    ("Web/ウェブ", ["Web", "web", "ウェブ", "ウエブ"]),
    ("Eメール/メール", ["Eメール", "e-mail", "E-mail", "Email", "email", "電子メール"]),
    ("こと/事", ["こと", r"(?<=[るたいう])事(?![件業務情柄例項象実])"]),
    ("とき/時", [r"(?<=[るたい])とき", r"(?<=[るたい])時(?![間刻代点期計系])"]),
    ("できる/出来る", ["でき(?=[るまなた])", "出来(?=[るまなた])"]),
    ("ください/下さい", ["ください", "下さい"]),
    ("わかる/分かる", ["わか(?=[るりらっ])", "分か(?=[るりらっ])"]),
    ("すべて/全て", ["すべて", "全て"]),
    ("さまざま/様々", ["さまざま", "様々"]),
    ("いろいろ/色々", ["いろいろ", "色々"]),
    ("たとえば/例えば", ["たとえば", "例えば"]),
    ("さらに/更に", ["さらに", "更に"]),
    ("すでに/既に", ["すでに", "既に"]),
    ("ほとんど/殆ど", ["ほとんど", "殆ど"]),
    ("または/又は", ["または", "又は"]),
    ("および/及び", ["および", "及び"]),
    ("ただし/但し", ["ただし", "但し"]),
    ("したがって/従って", ["したがって", r"(?<![にを])従って"]),
    # 「平等」「同等」「一等」など、等が熟語の一部になっているものは除く
    ("など/等", ["など", r"(?<=[ぁ-んァ-ヴー一-龥])(?<![平同均対上高初中劣優特一二三何])等(?![しく号価級分])"]),
    ("ように/様に", ["ように", "様に"]),
    ("行う/行なう", ["行う", "行なう"]),
    ("表す/表わす", ["表す", "表わす"]),
    ("申し込み/申込み", ["申し込み", "申込み"]),
    ("取り扱い/取扱い", ["取り扱い", "取扱い"]),
    ("打ち合わせ/打合せ", ["打ち合わせ", "打合せ"]),
    ("問い合わせ/問合せ", ["問い合わせ", "問合せ", "問い合せ"]),
    ("組み込み/組込み", ["組み込み", "組込み"]),
    ("書き込み/書込み", ["書き込み", "書込み"]),
    ("読み込み/読込み", ["読み込み", "読込み", "読込"]),
    ("引数/引き数", ["引数", "引き数"]),
    ("戻り値/戻値/返り値", ["戻り値", "戻値", "返り値"]),
    ("Copy-on-Write/コピーオンライト", ["Copy-on-Write", "copy-on-write", "Copy on Write", "コピーオンライト", "CoW"]),
    ("ガベージコレクション/GC", ["ガベージコレクション", "ガーベジコレクション", "ガベージコレクタ"]),
    ("ハッシュテーブル/ハッシュ表", ["ハッシュテーブル", "ハッシュ表"]),
    ("JSON/Json", ["JSON", "Json"]),
    ("か月/ヶ月/カ月", ["か月", "ヶ月", "カ月", "ヵ月", "ケ月", "箇月"]),
]

# 文体の要素
STYLE_SETS: list[tuple[str, list[str]]] = [
    ("一人称", ["私たち", "私", "僕", "筆者", "著者", "我々", "われわれ", "わたし"]),
    ("読者の呼び方", ["あなた", "読者の皆さん", "読者のみなさん", "皆さん", "みなさん", "読者"]),
    ("行動の促し", ["しましょう", "してください", "すること。", "してみてください", "してみましょう"]),
    ("読点", ["、", "，", ","]),
    ("句点", ["。", "．"]),
    ("丸かっこ", ["（", "("]),
    ("感嘆符", ["！", "!"]),
    ("疑問符", ["？", "?"]),
]


# 文体の要素のうち、そのまま数えると誤検出するもの（表示は左の文字のまま）
STYLE_PATTERNS = {
    ",": r"(?<!\d),|,(?!\d)",  # 3,000 のような桁区切りは読点として数えない
}


def count_patterns(text: str, patterns: list[str]) -> dict[str, int]:
    out = {}
    for p in patterns:
        n = len(re.findall(p, text))
        if n:
            out[p] = n
    return out


def readable(pattern: str) -> str:
    """正規表現を表示用の語に戻す（先読み・後読みを取り除く）。"""
    s = re.sub(r"\(\?<?[=!][^)]*\)", "", pattern)
    s = s.replace("[1-9]", "1").replace("[一二三四五六七八九]", "一")
    return s


def katakana_variants(lines) -> list[dict]:
    groups: dict[str, Counter] = defaultdict(Counter)
    where: dict[str, list[int]] = defaultdict(list)
    for no, _, body in lines:
        for w in KATAKANA_WORD.findall(body):
            groups[normalize_katakana(w)][w] += 1
            if len(where[w]) < 3:
                where[w].append(no)
    result = []
    for key, c in groups.items():
        if len(c) > 1:
            result.append({"forms": dict(c.most_common()),
                           "lines": {w: where[w] for w in c}})
    return sorted(result, key=lambda r: -sum(r["forms"].values()))


def alphabet_variants(lines) -> list[dict]:
    groups: dict[str, Counter] = defaultdict(Counter)
    where: dict[str, list[int]] = defaultdict(list)
    for no, _, body in lines:
        for w in ALPHA_WORD.findall(body):
            if len(w) < 3:
                continue
            groups[w.lower().replace("-", "").replace(".", "")][w] += 1
            if len(where[w]) < 3:
                where[w].append(no)
    result = []
    for key, c in groups.items():
        if len(c) > 1:
            result.append({"forms": dict(c.most_common()),
                           "lines": {w: where[w] for w in c}})
    return sorted(result, key=lambda r: -sum(r["forms"].values()))


def spacing_by_word(lines) -> list[dict]:
    """同じ英数字の語で、和文との間にスペースを入れたり入れなかったりしているもの。"""
    jp = r"[ぁ-んァ-ヴー一-龥]"
    word = r"[A-Za-z0-9][A-Za-z0-9.+#-]*"
    with_space: Counter = Counter()
    without: Counter = Counter()
    for _, kind, body in lines:
        for m in re.finditer(f"(?<={jp}) ({word})|({word}) (?={jp})", body):
            with_space[m.group(1) or m.group(2)] += 1
        for m in re.finditer(f"(?<={jp})({word})|({word})(?={jp})", body):
            without[m.group(1) or m.group(2)] += 1
    result = []
    for w in set(with_space) & set(without):
        if re.fullmatch(r"[0-9.]+", w):
            continue  # 数字は単位や助数詞との組み合わせが多いので除外
        result.append({"word": w, "スペースあり": with_space[w], "スペースなし": without[w]})
    return sorted(result, key=lambda r: -(r["スペースあり"] + r["スペースなし"]))[:15]


JP = r"[ぁ-んァ-ヴー一-龥]"

# 数字と組み合わせる助数詞。算用数字（1つ）と漢数字（一つ）の揺れを見る
COUNTERS = ["つ", "個", "回", "度", "文字", "行", "か所", "箇所", "種類", "番目", "件",
            "点", "倍", "桁", "本", "台", "人", "通り", "段", "組", "列"]

# 原語の語尾が -er / -or / -ar の語（長音を付けるか省くかが分かれる語）の語幹
CHOON_STEMS = [
    "アクセサ", "アダプタ", "イテレータ", "インストーラ", "インタプリタ", "エディタ",
    "エミュレータ", "オペレータ", "カウンタ", "キャラクタ", "クラスタ", "ゲッタ",
    "コネクタ", "コンストラクタ", "コントローラ", "コンパイラ", "コンピュータ", "サーバ",
    "シミュレータ", "シリアライザ", "ジェネレータ", "スキャナ", "スケジューラ", "セッタ",
    "セレクタ", "センサ", "タイマ", "デコーダ", "デコレータ", "デストラクタ", "デバッガ",
    "ドライバ", "トリガ", "ハンドラ", "バッファ", "バリデータ", "パーサ", "パラメータ",
    "フィルタ", "フォルダ", "フッタ", "ブラウザ", "プリンタ", "プロセッサ", "プロバイダ",
    "ヘッダ", "ポインタ", "マネージャ", "モニタ", "ユーザ", "リスナ", "リンカ", "ルータ",
    "レイヤ", "レジスタ", "レンダラ", "ローダ", "ワーカ",
]
UNITS = ["KiB", "MiB", "GiB", "KB", "MB", "GB", "TB", "ms", "ns", "μs", "px", "バイト",
         "ビット", "Hz", "GHz", "MHz", "%"]


def numeral_variants(text: str) -> list[dict]:
    """同じ助数詞で、算用数字と漢数字の両方が使われているもの。"""
    out = []
    for c in COUNTERS:
        arabic = len(re.findall(rf"(?<![0-9.,])[1-9]{c}", text))
        kanji = len(re.findall(rf"(?<![一二三四五六七八九十百千万第])[一二三四五六七八九]{c}", text))
        if arabic and kanji:
            out.append({"counter": c, "算用数字": arabic, "漢数字": kanji})
    return sorted(out, key=lambda r: -(r["算用数字"] + r["漢数字"]))


def choon_policy(text: str) -> dict:
    """-er / -or / -ar の語で、長音を付けている語と省いている語。"""
    with_choon, without = Counter(), Counter()
    for stem in CHOON_STEMS:
        a = len(re.findall(stem + "ー", text))
        b = len(re.findall(stem + "(?![ーァ-ヴ])", text))
        if a:
            with_choon[stem + "ー"] = a
        if b:
            without[stem] = b
    return {"長音あり": dict(with_choon.most_common()), "長音なし": dict(without.most_common())}


def unit_spacing(text: str) -> list[dict]:
    """数値と単位の間のスペースが、同じ単位で揺れているもの。"""
    out = []
    for u in UNITS:
        spaced = len(re.findall(rf"[0-9] {re.escape(u)}(?![A-Za-z])", text))
        tight = len(re.findall(rf"[0-9]{re.escape(u)}(?![A-Za-z])", text))
        if spaced and tight:
            out.append({"unit": u, "スペースあり": spaced, "スペースなし": tight})
    return out


def version_spacing(text: str) -> dict[str, int]:
    """「PHP 8.5 から」「PHP 8.5から」のように、名前＋番号の後ろのスペースの有無。"""
    pat = r"[A-Za-z][A-Za-z+#.]* [0-9]+(?:\.[0-9]+)*"
    # 「430行」「20万要素」のような数量を除くため、後ろがひらがな（助詞）の場合だけ数える
    return {
        "スペースあり": len(re.findall(pat + r" (?=[ぁ-ん])", text)),
        "スペースなし": len(re.findall(pat + r"(?=[ぁ-ん])", text)),
    }


def spacing_around_code(raw_texts: list[str]) -> dict[str, int]:
    """インラインコード（`code`）と和文の間のスペースの有無を、前後それぞれで数える。

    バッククォートの対を先頭から順に確定させる。そうしないと、あるコードの
    閉じ記号と次のコードの開き記号を1つのコードとして数えてしまう。
    """
    jp = re.compile(JP)
    spaced = tight = 0
    for text in raw_texts:
        for line in text.splitlines():
            for m in re.finditer(r"`[^`]+`", line):
                before, after = line[:m.start()], line[m.end():]
                if before:
                    if jp.match(before[-1]):
                        tight += 1
                    elif before.endswith(" ") and len(before) > 1 and jp.match(before[-2]):
                        spaced += 1
                if after:
                    if jp.match(after[0]):
                        tight += 1
                    elif after.startswith(" ") and len(after) > 1 and jp.match(after[1]):
                        spaced += 1
    return {"スペースあり": spaced, "スペースなし": tight}


def spacing_between_scripts(lines) -> dict[str, int]:
    """和文と英字の間のスペースの有無。数字は「3点」「2026年」のように、スペースを
    入れる方針の文書でも詰めて書くことが多いので数えない。"""
    jp = r"[ぁ-んァ-ヴー一-龥]"
    al = r"[A-Za-z]"
    text = "\n".join(b for _, k, b in lines if k != "table")
    return {
        "スペースあり": len(re.findall(f"{jp} {al}|{al} {jp}", text)),
        "スペースなし": len(re.findall(f"{jp}{al}|{al}{jp}", text)),
    }


# ---------------------------------------------------------------------------
# 構造・リンク・文字（KOZO-02〜04、MOJI-11）
# ---------------------------------------------------------------------------

VAGUE_LINK_TEXT = {"こちら", "ここ", "こちらのページ", "このページ", "リンク", "こちらをクリック",
                   "here", "click here", "link", "this page"}
VAGUE_ALT_TEXT = {"画像", "図", "写真", "スクリーンショット", "image", "img", "screenshot", "alt"}
# 丸囲み数字など、ローマ数字、かっこ付き・囲み文字、組文字（単位など）
ENV_DEPENDENT = re.compile("[\u2460-\u24ff\u2160-\u217f\u3200-\u32ff\u3300-\u33ff]")


def structure_checks(name: str, text: str) -> dict[str, list]:
    """見出しの階層の飛び、画像の代替テキスト、リンクテキスト、環境依存文字を集める。"""
    out: dict[str, list] = {"heading_skips": [], "images_without_alt": [],
                            "vague_links": [], "env_dependent_chars": []}
    in_code = False
    in_front = text.startswith("---\n")
    prev_level = 0
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        where = f"{name}:{no}"
        if in_front:
            if no > 1 and line == "---":
                in_front = False
            continue
        if FENCE.match(line.strip()):
            in_code = not in_code
            continue
        if REVIEW_BLOCK_START.match(line) and re.match(r"^//(list|emlist|cmd|source|listnum|emlistnum)", line):
            in_code = True
            continue
        if in_code:
            if REVIEW_BLOCK_END.match(line):
                in_code = False
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line) or re.match(r"^(={1,6})(?:\[.*?\])?\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            if prev_level and level > prev_level + 1:
                out["heading_skips"].append({"where": where, "from": prev_level, "to": level,
                                             "heading": m.group(2).strip()})
            prev_level = level
        body = INLINE_CODE_MD.sub(" ", line)
        for m in re.finditer(r"!\[([^\]]*)\]\([^)]*\)", body):
            alt = m.group(1).strip()
            if not alt or alt.lower() in VAGUE_ALT_TEXT:
                out["images_without_alt"].append({"where": where, "alt": alt})
        for m in re.finditer(r"(?<!!)\[([^\]]+)\]\([^)]*\)", body):
            label = m.group(1).strip()
            if label.lower() in VAGUE_LINK_TEXT:
                out["vague_links"].append({"where": where, "text": label})
        for m in re.finditer(r"@<href>\{[^,}]*,\s*([^}]*)\}", body):
            if m.group(1).strip().lower() in VAGUE_LINK_TEXT:
                out["vague_links"].append({"where": where, "text": m.group(1).strip()})
        chars = ENV_DEPENDENT.findall(body)
        if chars:
            out["env_dependent_chars"].append({"where": where, "chars": "".join(dict.fromkeys(chars))})
    return out


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------

def analyze(files: list[Path]) -> dict:
    lines = []
    raw_texts = []
    structure: dict[str, list] = {}
    for f in files:
        # BOM 付き UTF-8（Windows のメモ帳など）でもフロントマターを判定できるよう utf-8-sig で読む
        original = f.read_text(encoding="utf-8-sig", errors="replace")
        for key, found in structure_checks(f.name, original).items():
            structure.setdefault(key, []).extend(found)
        text = unicodedata.normalize("NFC", original)
        raw_texts.append(re.sub(r"```.*?```", "", text, flags=re.S))
        lines.extend((f"{f.name}:{no}", k, b) for no, k, b in extract_lines(text))
    body_text = "\n".join(b for _, k, b in lines)

    keitai, jotai, _ = sentence_endings(lines)
    majority = "敬体" if len(keitai) >= len(jotai) else "常体"
    minority = jotai if majority == "敬体" else keitai

    notation = []
    for name, pats in VARIANT_SETS:
        c = count_patterns(body_text, pats)
        if len(c) > 1:
            notation.append({"name": name, "counts": {readable(k): v for k, v in c.items()}})

    style = []
    for name, pats in STYLE_SETS:
        suffix = r"(?=[はがのもにをと、])" if name == "一人称" else ""
        regex = {(STYLE_PATTERNS[p] if p in STYLE_PATTERNS else re.escape(p) + suffix): p
                 for p in pats}
        c = {regex[k]: v for k, v in count_patterns(body_text, list(regex)).items()}
        # 一人称は後ろに助詞を要求しているので、「私」は「私たち」に一致しない（差し引かない）
        if name == "読者の呼び方":
            for longer, shorter in (("読者の皆さん", "皆さん"), ("読者のみなさん", "みなさん")):
                if longer in c and shorter in c:
                    c[shorter] -= c[longer]
                    if c[shorter] <= 0:
                        del c[shorter]
            if "読者" in c:
                c["読者"] -= c.get("読者の皆さん", 0) + c.get("読者のみなさん", 0)
                if c["読者"] <= 0:
                    del c["読者"]
        if len(c) > 1 or name in ("一人称", "読者の呼び方"):
            if c:
                style.append({"name": name, "counts": {k.replace("\\", ""): v for k, v in c.items()}})

    return {
        "files": [str(f) for f in files],
        "sentence_endings": {
            "敬体": len(keitai),
            "常体": len(jotai),
            "多数派": majority,
            "少数派の文": [{"where": w, "kind": k, "sentence": s} for w, k, s in minority[:30]],
            "少数派の文の総数": len(minority),
        },
        "katakana_variants": katakana_variants(lines),
        "alphabet_variants": alphabet_variants(lines),
        "notation_variants": notation,
        "style_elements": style,
        "spacing_jp_alnum": spacing_between_scripts(lines),
        "spacing_by_word": spacing_by_word(lines),
        "spacing_around_code": spacing_around_code(raw_texts),
        "numeral_variants": numeral_variants(body_text),
        "choon_policy": choon_policy(body_text),
        "unit_spacing": unit_spacing(body_text),
        "version_spacing": version_spacing(body_text),
        "structure": structure,
    }


def print_report(r: dict) -> None:
    se = r["sentence_endings"]
    print("# 表記・文体の集計\n")
    print(f"対象: {', '.join(Path(f).name for f in r['files'])}\n")

    print("## 文末（敬体・常体）")
    print(f"敬体 {se['敬体']} 文 / 常体 {se['常体']} 文 → 多数派: {se['多数派']}")
    if se["少数派の文の総数"]:
        print(f"少数派の文: {se['少数派の文の総数']} 文（最大30件を表示。"
              "箇条書き・引用・会話文は意図的な場合があるので文脈で判断すること）")
        for m in se["少数派の文"]:
            print(f"  - {m['where']} [{m['kind']}] {m['sentence']}")
    print()

    def show_variants(title, items):
        print(f"## {title}")
        if not items:
            print("なし\n")
            return
        for it in items:
            forms = " / ".join(f"{w}（{n}）" for w, n in it["forms"].items())
            print(f"  - {forms}")
            for w, ls in it["lines"].items():
                print(f"      {w}: {', '.join(ls)}")
        print()

    show_variants("カタカナ語の表記ゆれ候補", r["katakana_variants"])
    show_variants("英字の表記ゆれ候補（大文字・小文字・記号）", r["alphabet_variants"])

    print("## 語の表記ゆれ候補（漢字・かな、送り仮名、英字・カタカナ、数字）")
    if r["notation_variants"]:
        for it in r["notation_variants"]:
            forms = " / ".join(f"{w}（{n}）" for w, n in it["counts"].items())
            print(f"  - {it['name']}: {forms}")
    else:
        print("なし")
    print()

    if r["numeral_variants"]:
        print("## 数字の表記ゆれ候補（同じ助数詞で算用数字と漢数字が混在）")
        for it in r["numeral_variants"]:
            c = it["counter"]
            print(f"  - 1{c}（{it['算用数字']}） / 一{c}（{it['漢数字']}）")
        print()

    cp = r["choon_policy"]
    if cp["長音あり"] and cp["長音なし"]:
        print("## 長音の方針の混在候補（-er / -or / -ar の語）")
        print("  - 長音あり: " + "、".join(f"{w}（{n}）" for w, n in cp["長音あり"].items()))
        print("  - 長音なし: " + "、".join(f"{w}（{n}）" for w, n in cp["長音なし"].items()))
        print()

    print("## 文体の要素")
    for it in r["style_elements"]:
        forms = " / ".join(f"{w}（{n}）" for w, n in it["counts"].items())
        print(f"  - {it['name']}: {forms}")
    sp = r["spacing_jp_alnum"]
    print(f"  - 和文と英字の間: スペースあり（{sp['スペースあり']}） / スペースなし（{sp['スペースなし']}）")
    vs = r["version_spacing"]
    if vs["スペースあり"] and vs["スペースなし"]:
        print(f"  - 名前＋番号（PHP 8.5 など）の後ろ: スペースあり（{vs['スペースあり']}） / スペースなし（{vs['スペースなし']}）")
    for it in r["unit_spacing"]:
        print(f"  - 数値と単位 {it['unit']} の間: スペースあり（{it['スペースあり']}） / スペースなし（{it['スペースなし']}）")
    sc = r["spacing_around_code"]
    print(f"  - 和文とインラインコードの間: スペースあり（{sc['スペースあり']}） / スペースなし（{sc['スペースなし']}）")
    if r["spacing_by_word"]:
        print("  - 和文との間のスペースが語によって揺れているもの（上位15語）:")
        for it in r["spacing_by_word"]:
            print(f"      {it['word']}: あり（{it['スペースあり']}） / なし（{it['スペースなし']}）")
    st = r.get("structure", {})
    if any(st.values()):
        print("\n## 構造・リンク・文字（KOZO-02〜04、MOJI-11）")
        for it in st["heading_skips"][:20]:
            print(f"  - 見出しの階層の飛び: {it['where']} レベル{it['from']} → レベル{it['to']}「{it['heading']}」")
        for it in st["images_without_alt"][:20]:
            shown = f"「{it['alt']}」" if it["alt"] else "なし"
            print(f"  - 画像の代替テキスト: {it['where']} {shown}")
        for it in st["vague_links"][:20]:
            print(f"  - 行き先のわからないリンクテキスト: {it['where']}「{it['text']}」")
        for it in st["env_dependent_chars"][:20]:
            print(f"  - 環境依存文字: {it['where']} {it['chars']}")
        for key, label in (("heading_skips", "見出しの階層の飛び"), ("images_without_alt", "画像の代替テキスト"),
                           ("vague_links", "リンクテキスト"), ("env_dependent_chars", "環境依存文字")):
            if len(st[key]) > 20:
                print(f"  （{label}はほかに {len(st[key]) - 20} 件）")
    print("\n件数は候補。熟語の一部や本来の意味での使用（「事件」「時間」など）を"
          "完全には除外できないので、スキルが文脈で判断すること。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    args.files = [f for f in args.files
                  if not f.name.startswith("._") and "__MACOSX" not in f.parts]
    if not args.files:
        print("対象の原稿がありません。", file=sys.stderr)
        return 1
    for f in args.files:
        if not f.is_file():
            print(f"ファイルが見つかりません: {f}", file=sys.stderr)
            return 1
    r = analyze(args.files)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print_report(r)
    return 0


if __name__ == "__main__":
    # リダイレクト先が cp932 などになる環境（日本語版 Windows）でも UTF-8 で出力する
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # head などに渡しても例外を出さない
    sys.exit(main())
