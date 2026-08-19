# 作業用 private GCS（サービスと分離）

最終更新: 2026-08-19

このリポジトリは論文の再現パイプラインであり、Cloud Run・公開 CDN・ユーザー upload 用のバケットは**持たない**。  
Git に載せない作業データ（FitRec 原データなど）の正本だけを、下記の lab バケットに置く。

## バケット

| バケット | 用途 | 公開 | 誰が読むか |
|---|---|---|---|
| **`gs://grad-lab`** | **作業用（ローカルの `data/` など）** | **非公開・公開防止オン** | **自分の gcloud と、明示した Cloud Agent のみ** |

環境変数は `GRAD_LAB_BUCKET` だけ使う。`GCS_BUCKET` や `*_GCS_BUCKET` は使わない（本リポジトリに本番用定数はない）。

GCP プロジェクトは `gcloud` のデフォルト（作成時は `gpx-analytics-service`）。新プロジェクトは作らない。

## サービスバケット拒否リスト

コードと docs を検索した結果、**本番 GCS・公開バケット・Cloud Run env のバケット名は 0 件**。  
同期スクリプトは次を拒否する。

- 空のバケット名
- `-lab` で終わらない名前（誤って本番名を入れた場合の止め）

lab バケット名をデプロイスクリプトや定数ファイルに書いてはいけない（本リポジトリに該当ファイルはない）。

## いまローカルにあるもの（2026-08-18 計測）

| パス | おおよその量 | 既定の同期 |
|---|---|---|
| `data/`（CSV・期待値。`endomondoHR.json` を除く） | 2.8 MB | する |
| `results/` | 64 KB | する |
| `data/endomondoHR.json` | gitignore．正本は `gs://yamap-gpx-lab/research/data/endomondoHR.json`（`lab_assets.json`）．ローカルには残さない．スクリプトは GCS からストリームする |

次は **同期しない**（秘密・認証・ゴミ）。

- `.env` / `.env.*`（本リポジトリには無い。lab にも載せない）
- `credentials.json`、サービスアカウント JSON、`GOOGLE_APPLICATION_CREDENTIALS` の鍵
- `*token*.json`、OAuth、API キー平文
- `.fernet_key`、秘密鍵、`*.pem`、`id_rsa`
- 認証用 DB
- `.DS_Store`、`__pycache__`

`.env` / 鍵ファイルは、パス検索ではリポジトリ内に見つからなかった。Kaggle キーは `run_all.sh` が `~/.kaggle/kaggle.json` を参照するだけで、lab には載せない。

## コマンド

```bash
bash tools/scripts/sync_lab_gcs.sh ensure
bash tools/scripts/sync_lab_gcs.sh push
bash tools/scripts/sync_lab_gcs.sh push --research   # 1GB 超。明示したときだけ
bash tools/scripts/sync_lab_gcs.sh pull
bash tools/scripts/sync_lab_gcs.sh status
```

## オブジェクト配置

```text
gs://grad-lab/
  data/     # CSV 等．endomondoHR.json は含めない
  results/  # 解析ログ

FitRec 原データは共有正本:
  gs://yamap-gpx-lab/research/data/endomondoHR.json
```

## 誰がどの認証でアクセスするか

| 主体 | 認証 | 何をするか |
|---|---|---|
| ノートPC | 個人 Google アカウントの `gcloud auth login` と ADC（`gcloud auth application-default login`） | `push` / `pull`。JSON 鍵は作らない |
| 自分のユーザー | lab バケットだけの `roles/storage.objectAdmin` | オブジェクトの読み書き |
| Cloud Agent / CI | Git だけで足りるなら GCS に触れない。足りないとき `lab_gcs.py boot` が Cursor OIDC → GCP WIF で `cursor-lab-reader` に化ける（JSON 鍵不要）。信頼条件は `sub==user:383361105` | 必要な prefix だけ pull / ストリーム |
| スマホ GCS コンソール | 個人アカウント | 一覧・個別ダウンロード。作業場ではない |
| スマホ Cursor Web | Git（エディタ）。実験は Cloud Agent | コードが見える。原データが要るとき Agent を起動すると WIF が付く |

Cloud Agent は、追跡済みの `data/*.csv` とスクリプトだけで再現パイプラインの大半が動く。6GB の FitRec JSON は毎回落とさない。`lab_gcs.py` 経由のストリームは WIF で自動認証する。Cursor Web のエディタだけでは Git しか見えない。

ネットワークを Allowlist only にしている場合: `sts.googleapis.com`、`iamcredentials.googleapis.com`、`storage.googleapis.com`、`www.googleapis.com`、`iam.googleapis.com`。

## `.env` と機密

- `.env` はマシンローカル（と、もし本番を持つなら Secret Manager）に置く。lab GCS には載せない。
- 作業データは private + 公開防止 + IAM で足りる。新しい暗号レイヤは足さない。
- GCP 認証は `.env` に JSON 鍵を書かない。PC は ADC。
- 別マシンの API キーは `.env.example` をコピーするか Secret Manager。GCS から `.env` を配らない。

## やってはいけないこと

- lab バケットを Cloud Run の env に足す（本リポジトリに Cloud Run は無い）
- サービスアカウント JSON をリポジトリ・lab・`.env` に置く
- ノートPC の ADC をファイルごとエージェントに同期する
- 1GB 超を `--research` なしで upload する
