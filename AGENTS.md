# GRAD — Cloud Agent / Cursor Web

実験データ（FitRec JSON など）の正本は `gs://yamap-gpx-lab` / `gs://grad-lab`。Git には載せない。

Cursor Web から起動した Cloud Agent は `lab_gcs.py` が Cursor OIDC → GCP WIF で読む。JSON 鍵は不要。

OIDC の mint 手順: https://cursor.com/docs/cloud-agent/identity
