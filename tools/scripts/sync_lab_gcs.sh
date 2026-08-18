#!/usr/bin/env bash
# Sync workstation-only files to the private lab bucket.
# This repo has no Cloud Run / public CDN buckets; still refuse non-lab names.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${LAB_GCS_REGION:-asia-northeast1}"
BUCKET="${GRAD_LAB_BUCKET:-grad-lab}"

# Production / public buckets found in this repo's code and docs: none.
# Keep the array so a future service name can be added without changing control flow.
SERVICE_BUCKETS=()

usage() {
  cat <<'EOF'
Usage: bash tools/scripts/sync_lab_gcs.sh <ensure|push|pull|ls|status> [--research] [--dry-run]

  ensure   Create the private lab bucket if missing (uniform access, no public).
  push     Local -> gs://grad-lab/ (default: data/ minus raw JSON, plus results/)
  pull     gs://grad-lab/ -> local
  ls       List bucket prefixes
  status   Show local vs remote sizes

  --research  Include data/endomondoHR.json under raw/ (large; >1 GB)
  --dry-run   Print rsync plan only

Env:
  GRAD_LAB_BUCKET   default grad-lab
  GCP_PROJECT       default: current gcloud project
  LAB_GCS_REGION    default asia-northeast1
EOF
}

die() { echo "error: $*" >&2; exit 1; }

assert_lab_bucket() {
  local name
  [[ -n "$BUCKET" ]] || die "empty bucket name"
  if [[ "$BUCKET" != *-lab ]]; then
    die "refusing bucket '${BUCKET}': name must end with -lab. Set GRAD_LAB_BUCKET."
  fi
  for name in "${SERVICE_BUCKETS[@]+"${SERVICE_BUCKETS[@]}"}"; do
    if [[ "$BUCKET" == "$name" ]]; then
      die "refusing to use service bucket gs://${BUCKET}. Set GRAD_LAB_BUCKET to a lab name."
    fi
  done
}

need_gcloud() {
  command -v gcloud >/dev/null 2>&1 || die "gcloud not found"
  [[ -n "$PROJECT_ID" ]] || die "no GCP project; set GCP_PROJECT or gcloud config"
}

EXCLUDE_REGEX='(.*/)?(\.env|\.env\..*|\.fernet_key|credentials\.json|.*token.*\.json|users\.db|users\.json|\.DS_Store|__pycache__/.*|endomondoHR\.json)$'

INCLUDE_RESEARCH=0
DRY_RUN=0

ARGS=()
for arg in "$@"; do
  case "$arg" in
    --research) INCLUDE_RESEARCH=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) ARGS+=("$arg") ;;
  esac
done

CMD="${ARGS[0]:-}"
[[ -n "$CMD" ]] || { usage; exit 1; }

assert_lab_bucket
need_gcloud

ensure_bucket() {
  if gcloud storage buckets describe "gs://${BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "bucket exists: gs://${BUCKET}"
  else
    echo "creating private lab bucket gs://${BUCKET} ..."
    gcloud storage buckets create "gs://${BUCKET}" \
      --project="${PROJECT_ID}" \
      --location="${REGION}" \
      --uniform-bucket-level-access \
      --public-access-prevention
    gcloud storage buckets update "gs://${BUCKET}" \
      --project="${PROJECT_ID}" \
      --update-labels=purpose=workstation-lab,service=none,repo=grad
  fi
  if gcloud storage buckets get-iam-policy "gs://${BUCKET}" --project="${PROJECT_ID}" --format='json' \
      | grep -E 'allUsers|allAuthenticatedUsers' >/dev/null; then
    die "gs://${BUCKET} has a public IAM binding. Fix IAM before syncing."
  fi
}

grant_self_object_admin() {
  local account
  account="$(gcloud config get-value account 2>/dev/null || true)"
  [[ -n "$account" ]] || { echo "skip IAM: no gcloud account"; return 0; }
  echo "ensuring objectAdmin on gs://${BUCKET} for ${account}"
  gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --project="${PROJECT_ID}" \
    --member="user:${account}" \
    --role="roles/storage.objectAdmin" \
    --quiet >/dev/null
}

rsync_pair() {
  local src="$1"
  local dst="$2"
  [[ -e "$src" || "$src" == gs://* ]] || { echo "skip missing: $src"; return 0; }
  echo "rsync ${src} -> ${dst}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    gcloud storage rsync -r \
      --exclude="${EXCLUDE_REGEX}" --dry-run "$src" "$dst"
  else
    gcloud storage rsync -r \
      --exclude="${EXCLUDE_REGEX}" "$src" "$dst"
  fi
}

# Copy one file without following a tree rsync of data/ (avoids --delete wiping raw/).
cp_research_json() {
  local src="${ROOT}/data/endomondoHR.json"
  local dst="gs://${BUCKET}/raw/endomondoHR.json"
  [[ -e "$src" ]] || { echo "skip missing: $src"; return 0; }
  echo "cp ${src} -> ${dst} (--research)"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "dry-run: would copy research JSON to ${dst}"
    return 0
  fi
  gcloud storage cp "$src" "$dst"
}

run_push() {
  ensure_bucket
  grant_self_object_admin
  rsync_pair "${ROOT}/data" "gs://${BUCKET}/data"
  rsync_pair "${ROOT}/results" "gs://${BUCKET}/results"
  if [[ "$INCLUDE_RESEARCH" -eq 1 ]]; then
    cp_research_json
  fi
}

run_pull() {
  ensure_bucket
  mkdir -p "${ROOT}/data" "${ROOT}/results"
  rsync_pair "gs://${BUCKET}/data" "${ROOT}/data"
  rsync_pair "gs://${BUCKET}/results" "${ROOT}/results"
  if [[ "$INCLUDE_RESEARCH" -eq 1 ]]; then
    mkdir -p "${ROOT}/data"
    echo "cp gs://${BUCKET}/raw/endomondoHR.json -> ${ROOT}/data/endomondoHR.json"
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "dry-run: would copy research JSON locally"
    else
      gcloud storage cp "gs://${BUCKET}/raw/endomondoHR.json" "${ROOT}/data/endomondoHR.json"
    fi
  fi
}

run_ls() {
  ensure_bucket
  gcloud storage ls --recursive "gs://${BUCKET}" | head -200
}

run_status() {
  echo "local data/: $(du -sh "${ROOT}/data" 2>/dev/null | awk '{print $1}')"
  echo "local results/: $(du -sh "${ROOT}/results" 2>/dev/null | awk '{print $1}')"
  if [[ -e "${ROOT}/data/endomondoHR.json" ]]; then
    echo "local data/endomondoHR.json: present (not measured; --research only)"
  else
    echo "local data/endomondoHR.json: missing"
  fi
  if gcloud storage buckets describe "gs://${BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "remote gs://${BUCKET}:"
    gcloud storage du -s "gs://${BUCKET}/data" 2>/dev/null || echo "  data/: (missing)"
    gcloud storage du -s "gs://${BUCKET}/results" 2>/dev/null || echo "  results/: (missing)"
    gcloud storage du -s "gs://${BUCKET}/raw" 2>/dev/null || echo "  raw/: (missing)"
  else
    echo "remote gs://${BUCKET}: not created yet (run ensure)"
  fi
}

case "$CMD" in
  ensure)
    ensure_bucket
    grant_self_object_admin
    ;;
  push) run_push ;;
  pull) run_pull ;;
  ls) run_ls ;;
  status) run_status ;;
  *) usage; exit 1 ;;
esac
