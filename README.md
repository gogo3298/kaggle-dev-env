# kaggle-dev-env

Kaggle notebook 互換の Docker 環境を手元で再現し、推論・学習の両方を 1 つのコンテナで行えるようにした構成です。`dev/` 以下にあるコードやデータはそのまま `/kaggle/dev` としてコンテナにマウントされます。

## 要件

- [ ] kaggle notebook の実行環境と同様の環境で開発ができる
- [ ] コマンドにより kaggle のデータ取得、学習、notebook の提出を自動化できる
- [ ] mlflow による実験管理ができる
- [ ] dvc により実験データ管理ができる

## TODO

* kaggle notebook の実行環境よりもリッチな環境で学習ができる

## ディレクトリ構成

```
.
├── config/                   # Kaggle 関連の .env を格納
│   ├── kaggle.env            # 共有できる競技設定
│   └── kaggle.credentials.env# 個人の認証情報（Git 管理外）
├── data/
│   ├── input/                # ダウンロードしたコンペデータ
│   └── working/              # ローカル出力（コンテナの /kaggle/working）
├── dev/                      # /kaggle/dev にマウントされる作業領域
│   ├── input/                # /kaggle/input（read only）としてマウント
│   └── working/              # /kaggle/working としてマウント
├── scripts/                  # Kaggle API をラップした補助スクリプト
└── docker-compose.yml        # 作業用コンテナの定義
```

## 設定ファイル

- `config/kaggle.env` : コンペごとの設定を記述します。Git 共有を想定しており、`config/examples/*.env` をコピーして利用します。
- `config/kaggle.credentials.env` : `KAGGLE_USERNAME` / `KAGGLE_KEY` を保存します。`.gitignore` 済みのため実際の値はコミットしません。

主な環境変数:

| 変数 | 役割 |
| --- | --- |
| `KAGGLE_COMPETITION` | `kaggle competitions download` と `push_notebook.py` が参照するコンペ識別子。 |
| `KAGGLE_DOWNLOAD_DIR` | デフォルトの保存先。未指定時は `data/input/<competition>`。 |
| `KAGGLE_INPUT_DATASETS` | 追加で取得したい公開データセットを `owner/dataset[:path]` 形式で列挙。 |
| `KAGGLE_NOTEBOOK_OWNER` | Notebook ダウンロード対象のユーザー。省略時は `KAGGLE_USERNAME`。 |

## 主要スクリプトと用途

| スクリプト | 役割 | 代表的なコマンド |
| --- | --- | --- |
| `scripts/download_competition_data.py` | コンペ本体および `KAGGLE_INPUT_DATASETS` に列挙したデータを `data/input/` 以下へ取得する。 | `uv run python scripts/download_competition_data.py --config config/kaggle.env --secrets config/kaggle.credentials.env` |
| `scripts/download_notebooks.py` | Kaggle 上の公開/非公開 Notebook を `dev/` に同期する。 | `uv run python scripts/download_notebooks.py --config config/kaggle.env --owner <owner> --destination dev/notebooks/<owner>` |
| `scripts/push_notebook.py` | ローカル Notebook を Kaggle Kernel として push する。 | `uv run python scripts/push_notebook.py --config config/kaggle.env --secrets config/kaggle.credentials.env --notebook dev/exp001.ipynb` |

## 使い方

### 前提

* Docker
  * https://docs.docker.com/engine/install/
* Docker Compose V2 (`docker compose` コマンドが利用できる)
* uv（Python パッケージ/環境マネージャ）
  * [公式インストール手順](https://docs.astral.sh/uv/getting-started/installation/)
  * 例: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### ツール類の依存パッケージをインストール

```bash
# 依存パッケージをインストール
uv sync
```
### コンテナを起動する

```bash
# バックグラウンドで起動
docker compose up -d workspace
```

`docker compose exec workspace bash` でコンテナ内シェルに入ります。作業終了後は `docker compose down` で停止してください。

`dev/` 以下のファイルはコンテナ内の `/kaggle/` で参照できます。`dev/input` → `/kaggle/input`（read only）、`dev/working` → `/kaggle/working` にマッピングされるため、用途を 1 つのコンテナで整理できます。

### コンペデータのダウンロード

Kaggle API のユーザー名・キーおよびコンペ識別子は Git に含めない `.env` 形式のコンフィグファイルで管理します。`scripts/download_competition_data.py` がこのファイルを読み、`kaggle competitions download` を実行します。

1. Kaggle のアカウントページ（Profile → Account）から「Create New API Token」をクリックし、`username` と `key` を取得します。
2. 例として `config/examples/playground-series-s5e12.env` をコピーします。

   ```bash
   cp config/examples/playground-series-s5e12.env config/kaggle.env
   ```

3. `config/kaggle.env` を開き、コンペ識別子や `KAGGLE_DOWNLOAD_DIR` などの共有設定を記載します（認証情報は書かない）。
4. `config/examples/kaggle.credentials.env.example` をコピーして `config/kaggle.credentials.env` を作成し、`KAGGLE_USERNAME` と `KAGGLE_KEY` を記入します。このファイルは `.gitignore` 済みのため Git にコミットされません。

   ```bash
   cp config/examples/kaggle.credentials.env.example config/kaggle.credentials.env
   ```

5. 追加で他の公開データセットも取得したい場合は `KAGGLE_INPUT_DATASETS` にカンマ区切りで `owner/dataset` を列挙します。`owner/dataset:custom/path` のように末尾へパスを指定すれば保存先を上書きできます。
6. Kaggle CLI が利用できる環境（このリポジトリの uv 管理環境や Docker コンテナ）で以下を実行します。

   ```bash
   uv run python scripts/download_competition_data.py --config config/kaggle.env
   ```

   `uv run` は `pyproject.toml` に記載した `kaggle` 依存を自動で解決するため、CLI を別途インストールする必要はありません。省略すれば `data/input/<competition>` に保存され、`--destination` で出力先を上書きできます。

   Kaggle CLI が ZIP で配布するファイルは同ディレクトリ内に自動で展開されるため、取得後すぐに `/kaggle/input` から利用できます。

   `KAGGLE_INPUT_DATASETS` を指定した場合は、列挙したデータセットもそれぞれ `data/input/<dataset>` もしくは指定した保存先へ展開されます。`--secrets` で認証ファイルのパスを変更できます。

## 公開済み Notebook のダウンロード

Kaggle 上で公開した Notebook をローカルの `dev/` 以下へ取得するには、Kaggle API の認証情報を用意したうえで以下を実行します。

```bash
uv run python scripts/download_notebooks.py --config config/kaggle.env
```

既定では `KAGGLE_USERNAME` に紐づく公開 Notebook を `dev/` にダウンロードします。別のユーザー名で絞り込みたい場合は `.env` に `KAGGLE_NOTEBOOK_OWNER=<owner>` を追加するか、`--owner <owner>` を指定してください。

利用可能な主なオプション:

* `--include-private` : 認証済みのユーザーがアクセスできる非公開 Notebook も含めて取得します。
* `--overwrite` : 既に同名のファイルが存在していても上書きします（既定ではスキップ）。
* `--destination <path>` : 保存先ディレクトリ（既定は `dev/`）。
* `--kernel <owner/slug>` : 特定の Notebook だけをダウンロードします。`/` を含まない場合は `--owner` あるいは `KAGGLE_USERNAME` を補います。
* `--secrets <path>` : Kaggle 認証情報を格納したファイル（既定は `config/kaggle.credentials.env`）。

### 具体例

```bash
# 自分の公開 Notebook をまとめて dev/ に取得
uv run python scripts/download_notebooks.py

# 指定ユーザーの Notebook を別フォルダに取得
uv run python scripts/download_notebooks.py --owner masayakawamata --destination dev/notebooks/masaya

# 特定の Notebook を取得
uv run python scripts/download_notebooks.py --owner masayakawamata --kernel s5e12-eda-xgb-competition-starter

# 非公開 Notebook も含めて再ダウンロード
uv run python scripts/download_notebooks.py --include-private --overwrite
```

## Notebook を Kaggle へ push する

ローカルで編集した Notebook を Kaggle 上の Kernel として push するスクリプトを用意しています（提出はお好みのタイミングで Kaggle UI/CLI から行ってください）。

```bash
uv run python scripts/push_notebook.py \
  --config config/kaggle.env \
  --secrets config/kaggle.credentials.env \
  --notebook dev/exp001.ipynb \
  --slug exp001-notebook \
  --competition playground-series-s5e12
```

主なオプション:

* `--slug` : Kaggle 上の Kernel 名（`<username>/<slug>` の `slug` 部分）。
* `--title` : Kernel タイトル（省略時はノートブック名から自動生成）。
* `--competition` : コンペ識別子。メタデータに利用されます（任意）。
* `--enable-gpu` / `--enable-internet` / `--private` : Kaggle 実行環境の設定。
* `--secrets` : 認証情報ファイルのパス（任意）。

`push_notebook.py` は一時ディレクトリに `kernel-metadata.json` を生成して `kaggle kernels push` を実行します。Kaggle の仕様上 Kernel のタイトルからスラッグが導出されるため、一致しない場合はスクリプトが自動的にタイトルを補正します。

