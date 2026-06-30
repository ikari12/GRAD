#!/usr/bin/env python3
"""
Verification Script
===================

各スタディスクリプトの出力から [KEY] 行を抽出し，
expected_values.json の期待値と比較する．

使い方:
    python verify.py results_study1.txt results_study2.txt results_study3.txt

出力形式:
    ✓ key_name: expected=X.XXX, got=X.XXX (within tolerance)
    ✗ key_name: expected=X.XXX, got=X.XXX (MISMATCH, tolerance=X.XX)
"""

import json
import os
import re
import sys


def load_expected_values(json_path):
    """expected_values.json を読み込み，フラットな辞書として返す．"""
    with open(json_path, "r") as f:
        data = json.load(f)

    flat = {}
    for study_name, entries in data.items():
        for key, spec in entries.items():
            flat[key] = spec
    return flat


def extract_key_values(file_paths):
    """
    結果ファイルから [KEY] 行を抽出する．
    形式: [KEY] key_name = value
    """
    results = {}
    key_pattern = re.compile(r"^\[KEY\]\s+(\S+)\s*=\s*(.+)$")

    for fpath in file_paths:
        if not os.path.exists(fpath):
            print(f"WARNING: File not found: {fpath}", file=sys.stderr)
            continue

        with open(fpath, "r") as f:
            for line in f:
                line = line.strip()
                match = key_pattern.match(line)
                if match:
                    key_name = match.group(1)
                    try:
                        value = float(match.group(2))
                    except ValueError:
                        value = match.group(2).strip()
                    results[key_name] = value

    return results


def verify(expected, actual):
    """
    期待値と実測値を比較し，結果を表示する．
    許容範囲内であれば ✓，そうでなければ ✗ を表示する．
    """
    matched = 0
    total = 0
    missing = 0

    # 期待値のキーをソートして表示
    for key in sorted(expected.keys()):
        spec = expected[key]
        exp_val = spec["value"]
        tolerance = spec["tolerance"]
        total += 1

        if key not in actual:
            print(f"  ? {key}: expected={exp_val}, got=MISSING")
            missing += 1
            continue

        got_val = actual[key]

        if isinstance(got_val, str):
            # 文字列の場合は完全一致で比較
            if str(exp_val) == got_val:
                print(f"  ✓ {key}: expected={exp_val}, got={got_val} (exact match)")
                matched += 1
            else:
                print(f"  ✗ {key}: expected={exp_val}, got={got_val} (MISMATCH)")
        else:
            diff = abs(got_val - exp_val)
            if diff <= tolerance:
                print(f"  ✓ {key}: expected={exp_val:.3f}, got={got_val:.3f} (within tolerance)")
                matched += 1
            else:
                print(
                    f"  ✗ {key}: expected={exp_val:.3f}, got={got_val:.3f} "
                    f"(MISMATCH, diff={diff:.4f}, tolerance={tolerance})"
                )

    # 実測値にあるが期待値にないキーを表示
    extra_keys = set(actual.keys()) - set(expected.keys())
    if extra_keys:
        print(f"\n  Info: {len(extra_keys)} additional keys not in expected_values.json:")
        for k in sorted(extra_keys):
            print(f"    {k} = {actual[k]}")

    return matched, total, missing


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify.py results_study1.txt [results_study2.txt] [results_study3.txt]")
        sys.exit(1)

    # expected_values.json のパスを決定
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, "data", "expected_values.json")

    if not os.path.exists(json_path):
        print(f"ERROR: {json_path} not found.", file=sys.stderr)
        sys.exit(1)

    expected = load_expected_values(json_path)
    actual = extract_key_values(sys.argv[1:])

    print("=" * 60)
    print("Verification Results")
    print("=" * 60)
    print()

    matched, total, missing = verify(expected, actual)

    print()
    print("=" * 60)
    print(f"Summary: {matched}/{total} values matched.")
    if missing > 0:
        print(f"  ({missing} expected values were missing from output)")
    print("=" * 60)


if __name__ == "__main__":
    main()
