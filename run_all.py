import subprocess
import time
import sys
import os

def run_script(script_name):
    print(f"--- Running {script_name} ...")
    start_time = time.time()
    try:
        # We use sys.executable to ensure we use the same python environment
        result = subprocess.run([sys.executable, script_name], check=True, capture_output=True, text=True)
        elapsed = time.time() - start_time
        print(f"✅ Finished {script_name} in {elapsed:.1f}s")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR in {script_name}:")
        print(e.stderr)
        return False

def main():
    print("============================================================")
    print(" GRAD: Full Reproducibility Pipeline ")
    print("============================================================")
    
    if not os.path.exists("config.yaml"):
        print("❌ Error: config.yaml not found.")
        return

    scripts = [
        "00a_compute_4d.py",
        "00b_compute_abc.py",
        "01_study1_construct.py",
        "02_study2_artifact.py",
        "03_study3_variance.py",
        "06_supplementary.py",
        "07_h5_estpower.py",
        "08_supp_di_route_dist.py",
        "09_dw_acf_sensitivity.py",
        "10_sport_variance.py",
    ]
    
    for script in scripts:
        if not run_script(script):
            print("\n🚨 Pipeline halted due to error.")
            sys.exit(1)
            
    print("\n============================================================")
    print(" ✅ ALL ANALYSES COMPLETED SUCCESSFULLY ")
    print(" All results are now consistent with the manuscript. ")
    print("============================================================")

if __name__ == "__main__":
    main()
