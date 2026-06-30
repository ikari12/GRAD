#!/bin/bash
# ============================================================
# Reproduction Pipeline: Download → Preprocess → Analyze → Verify
# ============================================================
# Usage: bash run_all.sh [--skip-download] [--skip-preprocess]
#
# ディレクトリ構成:
#   Yamap_GPX/
#   ├── data/fitrec/                 ← データのみ
#   │   ├── endomondoHR.json         ← Kaggle からDL（6GB）
#   │   ├── meixner_4d_indices.csv   ← 00a で生成
#   │   └── abc_metrics.csv          ← 00b で生成
#   └── research/                    ← 全コード
#       ├── data/                     ← CSV + 期待値
#       ├── results/                  ← 出力（txt + png）
#       ├── 00a_compute_4d.py        ← 前処理: Meixner 4D
#       ├── 00b_compute_abc.py       ← 前処理: ABC metrics
#       ├── 01_study1_construct.py
#       ├── 02_study2_artifact.py
#       ├── 03_study3_variance.py
#       ├── 04_verify.py
#       └── 05_figures.py            ← 論文用図の生成
#
# データソース: FitRec dataset (Kaggle: tientd95/fitrec-dataset)
# DL先: data/fitrec/endomondoHR.json
# 必要ツール: python3, pip3, kaggle CLI (データ未取得時のみ)
# ============================================================
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKIP_DOWNLOAD=0
SKIP_PREPROCESS=0
for arg in "$@"; do
    case $arg in
        --skip-download) SKIP_DOWNLOAD=1 ;;
        --skip-preprocess) SKIP_PREPROCESS=1 ;;
    esac
done

# 全パスを明示（research/data は data/fitrec へのシンボリックリンク）
DATA_DIR="$SCRIPT_DIR/data"
RAW_JSON="$DATA_DIR/endomondoHR.json"
IDX_CSV="$DATA_DIR/meixner_4d_indices.csv"
ABC_CSV="$DATA_DIR/abc_metrics.csv"

echo "========================================"
echo "Research Reproduction Pipeline"
echo "========================================"
echo "  Project root : $PROJECT_ROOT"
echo "  Data dir     : $DATA_DIR"
echo "  Script dir   : $SCRIPT_DIR"
echo ""

# ============================================================
# Step 0: Dependencies
# ============================================================
echo "--- Step 0: Check dependencies ---"
python3 -c 'import numpy, scipy, sklearn, pandas' 2>/dev/null || {
    echo "Installing Python dependencies..."
    pip3 install -r requirements.txt
}
echo "  ✓ Python dependencies OK"
echo ""

# ============================================================
# Step 1: Data Download
# ============================================================
echo "--- Step 1: Data download ---"
if [ $SKIP_DOWNLOAD -eq 1 ]; then
    echo "  Skipped (--skip-download)"
elif [ -f "$RAW_JSON" ]; then
    echo "  ✓ endomondoHR.json already exists ($(du -h "$RAW_JSON" | cut -f1))"
else
    echo "  Downloading FitRec dataset from Kaggle..."
    echo "  (requires: pip install kaggle && ~/.kaggle/kaggle.json)"
    if ! command -v kaggle &>/dev/null; then
        echo "  ERROR: kaggle CLI not found. Install: pip3 install kaggle"
        echo "  Then place API key at ~/.kaggle/kaggle.json"
        exit 1
    fi
    kaggle datasets download -d tientd95/fitrec-dataset -p "$DATA_DIR" --unzip
    if [ ! -f "$RAW_JSON" ]; then
        # zip内のパスが異なる場合
        FOUND=$(find "$DATA_DIR" -name 'endomondoHR.json' -type f 2>/dev/null | head -1)
        if [ -n "$FOUND" ] && [ "$FOUND" != "$RAW_JSON" ]; then
            mv "$FOUND" "$RAW_JSON"
        else
            echo "  ERROR: endomondoHR.json not found after download"
            exit 1
        fi
    fi
    echo "  ✓ Download complete"
fi
echo ""

# ============================================================
# Step 2: Preprocessing
# ============================================================
echo "--- Step 2: Preprocessing ---"
if [ $SKIP_PREPROCESS -eq 1 ]; then
    echo "  Skipped (--skip-preprocess)"
else
    # Step 2a: Meixner 4D indices (DI, FI, RI, EI)
    if [ -f "$IDX_CSV" ]; then
        N_IDX=$(wc -l < "$IDX_CSV")
        echo "  ✓ meixner_4d_indices.csv exists ($N_IDX rows)"
        echo "    To regenerate, delete the file and rerun."
    else
        echo "  Computing Meixner 4D indices..."
        echo "  (processes 6GB JSON, ~10-20 min)"
        python3 "$SCRIPT_DIR/00a_compute_4d.py"
        echo "  ✓ meixner_4d_indices.csv created"
    fi

    # Step 2b: ABC metrics (GACD, GradSens, SpeedSens)
    if [ -f "$ABC_CSV" ]; then
        N_ABC=$(wc -l < "$ABC_CSV")
        echo "  ✓ abc_metrics.csv exists ($N_ABC rows)"
        echo "    To regenerate, delete the file and rerun."
    else
        echo "  Computing ABC metrics..."
        echo "  (processes 6GB JSON, ~10-20 min)"
        python3 "$SCRIPT_DIR/00b_compute_abc.py"
        echo "  ✓ abc_metrics.csv created"
    fi
fi

if [ ! -f "$IDX_CSV" ]; then
    echo "  ERROR: $IDX_CSV not found."
    exit 1
fi
if [ ! -f "$ABC_CSV" ]; then
    echo "  ERROR: $ABC_CSV not found."
    exit 1
fi
echo ""

# ============================================================
# Step 3: Analysis
# ============================================================
mkdir -p results

echo "--- Step 3: Study 1 — Construct Validity ---"
python3 01_study1_construct.py 2>&1 | tee results/study1.txt

echo ""
echo "--- Step 3: Study 2 — Artifact Detection ---"
python3 02_study2_artifact.py 2>&1 | tee results/study2.txt

echo ""
echo "--- Step 3: Study 3 — Variance Decomposition ---"
python3 03_study3_variance.py 2>&1 | tee results/study3.txt

# ============================================================
# Step 4: Verification
# ============================================================
echo ""
echo "========================================"
echo "Step 4: Verification"
echo "========================================"
python3 04_verify.py results/study1.txt results/study2.txt results/study3.txt

# ============================================================
# Step 5: Figure Generation
# ============================================================
echo ""
echo "========================================"
echo "Step 5: Figure Generation"
echo "========================================"
python3 05_figures.py
