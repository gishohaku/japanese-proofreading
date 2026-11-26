# 日本語校正スキル（japanese-proofreading）

技術書・技術記事・ドキュメントの日本語を校正・査読する Claude 用のスキルです。

textlint で機械的に検出できる誤りを先に洗い出し、そのうえで Claude が文脈の必要な判定と、テクニカルライティングの観点からの読みやすさの改善提案を行います。

## クイックスタート

1. スキルをインストールします（[インストール](#インストール)）。
2. Claude に原稿を渡して、次のように依頼します。

```
この原稿を校正してください。
この章を査読して、読みにくいところがあれば教えてください。
本の全章（chapters/*.re）で表記ゆれと文体の揺れを見てください。
chapter03.md を校正と査読の両方でチェックして、修正版もください。
```

結果は、重要度ごとの指摘の一覧で返ります。「修正版をください」と頼むと、原稿のコピーに修正を反映したファイルも作成します。

## 特徴

- **2層のチェック**：文・語・表記の正誤を見る「校正」と、段落・節の読みやすさを見る「査読」を分けて出力します。
- **重要度の区別**：校正の指摘は「誤り」「推奨」「任意」の3段階です。内容の食い違いなど、書き手に確かめてほしい点は「要確認」として分けて出します。査読の指摘はすべて「提案」で、読み手がつまずく箇所があるときだけ出します。修正版に反映するのは「誤り」「推奨」です。表記や文体の統一を頼んだ場合は、方針が決まった統一も反映します。
- **textlint との分担**：辞書や形態素解析で判定できるもの（送り仮名の誤り、ら抜き言葉、重言、記号など）は textlint が担当します。文脈が必要なもの（「は」と「が」、主述のねじれ、自動詞・他動詞の取り違えなど）と、textlint の誤検出の除外は Claude が担当します。
- **文書全体の統一**：章をまたいだ表記ゆれ、ですます調とである調の混在、一人称や読者の呼び方などの揺れを集計し、多数派またはユーザーの指定に合わせて統一案を出します。
- **ルールID**：すべての指摘にルールID（`KAKU-01`、`PW-02` など）が付き、根拠を確認できます。
- **対応形式**：Markdown、テキスト、Re:VIEW。コードブロックは対象外です。Word や PDF などは、Claude がテキストを抽出してから校正します。

## チェックする内容

### 校正

| 分類 | ID | 主な内容 |
|---|---|---|
| 格助詞・助詞 | KAKU, JOSHI | 「は」と「が」、助詞の重複、「の」の連続、接続助詞「が」、条件の表現、「〜たり」の対応 |
| 文の構造 | BUN | 語順、係り受け、主述のねじれ、並列、能動と受動、一文一義、読点、二重否定 |
| 送り仮名 | OKURI | 「送り仮名の付け方」に基づく本則・例外・許容 |
| 開く漢字 | HIRAKU | 形式名詞、補助動詞、副詞、接続詞、表外字 |
| 語彙・表記 | GOI | 外来語の表記、同音異義語、ら抜き・さ入れ・い抜き、重言、話し言葉、冗長表現、慣用句、固有名詞、誤字・脱字・誤変換、範囲・境界の表現、意味が揺れている語、読み手への配慮 |
| 文字・記号 | MOJI | 句読点、全角・半角、数字、単位、スペース、かっこ、文末のコロン、不可視文字、環境依存文字 |
| 構造・参照・リンク | KOZO | 見出しの階層、図表・脚注の参照、リンクテキスト、代替テキスト、UI 要素・キーの書き方 |
| 文書全体の統一 | TOITSU | 表記ゆれ、同じ対象の別名、文末（敬体・常体）、一人称・読者の呼び方、行動の促し方、記号・体裁、見出し |
| 内容の整合 | SEIGO | 本文とコード・図表の食い違い、章をまたいだ数値・名称の不一致、日付と曜日のずれ（「要確認」として出す）|

### 査読

| 分類 | ID | 主な内容 |
|---|---|---|
| 3C | TW | 正確（Correct）・明確（Clear）・簡潔（Concise）、定型的・機械的な書き方 |
| パラグラフライティング | PW | 1パラグラフ1トピック、トピックセンテンス、文の接続、段落の長さと順序、拾い読みテスト |
| 文章構成の型 | KATA | PREP、SDS、DESC、手順型、概念説明型 |

## インストール

### Claude Code

スキルのディレクトリを、個人用またはプロジェクト用のスキルディレクトリにコピーします。

```bash
# 個人用（すべてのプロジェクトで使う）
cp -r skills/japanese-proofreading ~/.claude/skills/

# プロジェクト用
cp -r skills/japanese-proofreading <プロジェクト>/.claude/skills/
```

### claude.ai

`.skill` ファイルを作成し、claude.ai のスキル設定からアップロードします。GitHub Actions の実行結果（Artifacts）からもダウンロードできます。

```bash
python3 scripts/package.py
# → dist/japanese-proofreading.skill
```

### 必要な環境

| 用途 | 必要なもの |
|---|---|
| 表記ゆれ・文体の集計（`consistency.py`）| Python 3.9 以降 |
| textlint（`lint.py`）| Python 3.9 以降、Node.js 20 以降、npm レジストリへの接続 |

初回実行時に textlint の依存関係（同義語辞書を含めて約 30MB）をインストールします。スキルのディレクトリが書き込み禁止の場合は、`~/.cache/japanese-proofreading/` にインストールします。インストール先は環境変数 `JAPANESE_PROOFREADING_CACHE` で変更できます。Node.js がない、または接続できない環境では、textlint を使わずにルール集だけで校正します。

macOS、Linux、Windows で動きます（CI で3つの OS とも確認しています）。Windows で `python3` が見つからない場合は、本書のコマンドの `python3` を `python` または `py -3` に読み替えてください。

## スクリプトだけを使う

Claude を使わずに、エディターや CI からスクリプトを直接実行できます。

```bash
# textlint の指摘を、ルールIDに対応付けて文ごとに表示
python3 skills/japanese-proofreading/scripts/lint.py chapters/*.md

# 表記ゆれ・文末・文体の要素を集計（長音の方針、数字と助数詞、単位やバージョン番号の前後のスペース、見出しの階層、リンクテキスト、環境依存文字など）
python3 skills/japanese-proofreading/scripts/consistency.py chapters/*.md
```

どちらも `--json` を付けると JSON で出力します。`lint.py` は既定で該当文を先頭80字に省略します。全文を表示するには `--full` を付けます。

回帰テストは次のとおりです。誤りを1文に1つずつ埋め込んだ原稿で、スクリプトが検出すべき誤りを検出できるかを確かめます。CI でも実行しています。

```bash
python3 tests/check_regression.py
```

Claude が文脈で判定するルール（「は」と「が」、主述のねじれ、誤変換など）は、スクリプトでは確かめられません。`tests/evals/evals.json` に、スキルを使った実行結果が満たすべき条件をまとめています。スキルやルール集を変更したときは、skill-creator などでこの評価を実行して、判定が変わっていないかを確かめてください。

textlint を直接使う場合は次のとおりです。

```bash
cd skills/japanese-proofreading/textlint
npm ci
npx textlint --config .textlintrc.json <原稿>
```

## 表記方針のカスタマイズ

既定の表記方針は次のとおりです。

- 外来語の語尾の長音は付ける（サーバー、ユーザー）
- 可能の「できる」、補助動詞（〜てください、〜ていただく）、形式名詞は開く
- 送り仮名は本則を優先する
- 句読点とかっこは全角を使う

方針を変える場合は、次の3か所を合わせて変更してください。一部だけを変えると、textlint の指摘と Claude の判定が矛盾します。

1. `textlint/prh/house.yml`：機械的に検出する語の辞書
2. `references/checklist.md`：「表記方針の既定値」
3. `references/rules/`：該当するルール

例：長音を省く方針にする場合は、`house.yml` の `GOI-01 長音` のエントリを削除し、`checklist.md` の既定値と `rules/goi.md` の GOI-01 を変更します。

## リポジトリの構成

```
.
├── skills/japanese-proofreading/       スキル本体
│   ├── SKILL.md                        スキルの手順
│   ├── references/
│   │   ├── checklist.md                全ルールの要点（校正で最初に読む）
│   │   ├── rules/                      カテゴリ別の詳細（必要なときだけ読む）
│   │   │   ├── joshi.md  bun.md  okuri.md  hiraku.md
│   │   │   └── goi.md  moji.md  toitsu.md  kozo.md
│   │   ├── review.md                   査読ルール
│   │   └── output-format.md            出力テンプレート
│   ├── scripts/
│   │   ├── lint.py                     textlint の実行と要約
│   │   └── consistency.py              表記ゆれ・文体の集計
│   └── textlint/                       textlint の設定と prh 辞書
├── examples/sample.md                  動作確認用の原稿
├── tests/                              回帰テスト（誤りを埋め込んだ原稿と期待値）、Claude の判定の評価（evals/）
├── scripts/package.py                  .skill ファイルの作成
└── .github/workflows/check.yml         CI
```

ルール集を「常に読むチェックリスト」と「必要なときだけ読む詳細」に分けているのは、スキル実行時のトークン消費を抑えるためです。

## 参考資料

- [文章校正まとめ（Qiita）](https://qiita.com/ariaki/items/008e0fea2eebb130e884)
- [テキスト校正くん（ics-creative/project-japanese-proofreading）](https://github.com/ics-creative/project-japanese-proofreading)
- [textlint-rule-preset-icsmedia](https://github.com/ics-creative/textlint-rule-preset-icsmedia)
- [textlint-rule-preset-ja-technical-writing](https://github.com/textlint-ja/textlint-rule-preset-ja-technical-writing)
- [textlint-rule-preset-jtf-style](https://github.com/textlint-ja/textlint-rule-preset-JTF-style)
- [textlint-rule-no-synonyms](https://github.com/textlint-ja/textlint-rule-no-synonyms)
- [textlint-rule-no-dropping-i](https://github.com/textlint-ja/textlint-rule-no-dropping-i)
- [textlint-rule-date-weekday-mismatch](https://github.com/textlint-rule/textlint-rule-date-weekday-mismatch)
- 送り仮名の付け方（昭和48年内閣告示第2号）
- 外来語の表記（平成3年内閣告示第2号）
- JTF日本語標準スタイルガイド
- [公用文作成の考え方（文化審議会建議、2022年）](https://www.bunka.go.jp/seisaku/bunkashingikai/kokugo/hokoku/pdf/93651301_01.pdf)
- [SmartHR Design System（記号の表記、操作手順の書き方）](https://smarthr.design/products/contents/)
- [デジタル庁デザインシステム（リンクテキスト）](https://design.digital.go.jp/dads/foundations/link-text/)

## 謝辞

このスキルは、次の資料・ソフトウェアの成果の上に成り立っています。公開してくださっている皆さまに感謝します。

- **株式会社アイ・シー・エス（ICS INC.）**：[テキスト校正くん](https://github.com/ics-creative/project-japanese-proofreading) の校正ルールの構成を参考にし、[textlint-rule-preset-icsmedia](https://github.com/ics-creative/textlint-rule-preset-icsmedia) の慣用句・重言の辞書を収録しています。
- **textlint と textlint-ja のコントリビューターの皆さま**：校正の機械的なチェックは [textlint](https://textlint.github.io/) と、[textlint-ja](https://github.com/textlint-ja) で公開されているルール・プリセットで行っています。
- **株式会社ワークスアプリケーションズ**：表記ゆれの検出に [Sudachi 同義語辞書](https://github.com/WorksApplications/SudachiDict) を利用しています。
- **日本翻訳連盟（JTF）**：文字・記号のルールは「JTF日本語標準スタイルガイド」に基づいています。
- **文化庁・内閣告示**：送り仮名は「送り仮名の付け方」、外来語は「外来語の表記」に基づいています。

ルール集の例文は、参考資料の文例をそのまま使わず、このリポジトリ用に書き起こしています。

## ライセンス

[MIT License](LICENSE)。Copyright (c) 2026 [技術書同人誌博覧会](https://gishohaku.dev)

収録している ICS MEDIA の辞書と、実行時に利用するパッケージのライセンスは [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。
