# サードパーティーのライセンス

このリポジトリは、次のサードパーティーのソフトウェア・辞書を収録、または実行時に利用しています。

## リポジトリに収録しているもの

### textlint-rule-preset-icsmedia

- 提供：株式会社アイ・シー・エス（ICS INC.）
- リポジトリ：<https://github.com/ics-creative/textlint-rule-preset-icsmedia>
- ライセンス：MIT License, Copyright (c) 2018 ICS INC.
- 収録しているファイル
  - `skills/japanese-proofreading/textlint/prh/icsmedia_idiom.yml`（元：`dict/prh_idiom.yml`）。「どおりで → 道理で」のエントリだけ、「規則どおりです」などの誤検出を避けるため、文頭・句読点の直後に限定するよう変更しています（変更箇所にコメントあり）
  - `skills/japanese-proofreading/textlint/prh/icsmedia_duplicate.yml`（元：`dict/prh_duplicate.yml`）。変更していません
- ライセンス全文：`skills/japanese-proofreading/textlint/prh/LICENSE-icsmedia`

## 実行時にインストールするもの

次のパッケージは `skills/japanese-proofreading/textlint/package.json` に記載しており、実行時に npm からインストールされます。リポジトリには含まれません。各パッケージのライセンスに従ってください。

| パッケージ | ライセンス | リポジトリ |
|---|---|---|
| textlint | MIT | <https://github.com/textlint/textlint> |
| @textlint/textlint-plugin-markdown | MIT | <https://github.com/textlint/textlint> |
| @textlint/textlint-plugin-text | MIT | <https://github.com/textlint/textlint> |
| textlint-filter-rule-comments | MIT | <https://github.com/textlint/textlint-filter-rule-comments> |
| textlint-plugin-review | MIT | <https://github.com/orangain/textlint-plugin-review> |
| textlint-rule-preset-ja-technical-writing | MIT | <https://github.com/textlint-ja/textlint-rule-preset-ja-technical-writing> |
| textlint-rule-preset-jtf-style | MIT | <https://github.com/textlint-ja/textlint-rule-preset-JTF-style> |
| textlint-rule-prh | MIT | <https://github.com/textlint-rule/textlint-rule-prh> |
| @textlint-ja/textlint-rule-no-synonyms | MIT | <https://github.com/textlint-ja/textlint-rule-no-synonyms> |
| sudachi-synonyms-dictionary | Apache-2.0 | <https://github.com/azu/sudachi-synonyms-dictionary> |

`sudachi-synonyms-dictionary` は、株式会社ワークスアプリケーションズの [Sudachi 同義語辞書](https://github.com/WorksApplications/SudachiDict)（Apache-2.0）をパッケージにしたものです。

形態素解析には、上記のパッケージが依存する kuromoji.js（Apache-2.0）と、その辞書（IPA 辞書由来）を利用しています。
