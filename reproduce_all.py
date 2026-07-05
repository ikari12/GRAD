import subprocess
import time
import os

scripts = [
    "00a_compute_4d.py",
    "00b_compute_abc.py",
    "01_study1_construct.py",
    "02_study2_artifact.py",
    "03_study3_variance.py",
    "07_h5_estpower.py",
    "08_supp_di_route_dist.py",
    "09_dw_acf_sensitivity.py",
    "10_sport_variance.py",
]

print("=== STARTING FULL PIPELINE REPRODUCTION ===")
for script in scripts:
    print(f"\n--- Running {script} ---")
    start_time = time.time()
    try:
        # Run script and capture output
        result = subprocess.run(["python3", script], capture_output=True, text=True, check=True)
        elapsed = time.time() - start_time
        print(f"✅ {script} completed in {elapsed:.2f}s")
        # Log first and last 5 lines of output to show it actually ran
        lines = result.stdout.splitlines()
        if lines:
            print("Output sample:")
            for line in lines[:5]: print(f"  {line}")
            if len(lines) > 10: print("  ...")
            for line in lines[-5:]: print(f"  {line}")
    except subprocess.CalledProcessError as e:
        print(f"❌ {script} FAILED")
        print(e.stderr)
        break

print("\n=== FULL REPRODUCTION FINISHED ===")
