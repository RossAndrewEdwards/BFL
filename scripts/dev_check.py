import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command, label, check=True):
    print(f"\n== {label} ==")
    result = subprocess.run(command, cwd=ROOT, text=True)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Run the checks this environment can support.")
    parser.parse_args()

    python = sys.executable
    run([python, "-m", "py_compile", "app.py", "scripts/smoke_tests.py"], "Python compile checks")
    run([python, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], "Python unittest suite")
    run([python, "scripts/smoke_tests.py"], "Flask smoke tests")

    print("\nAll available checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
