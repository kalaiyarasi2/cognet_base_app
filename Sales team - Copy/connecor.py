"""
connecor.py - Alias redirect script to run connector.py.
Handles the spelling typo 'connecor.py'.
"""
import sys
import subprocess
from pathlib import Path

def main():
    connector_script = Path(__file__).parent / "connector.py"
    cmd = [sys.executable, str(connector_script)] + sys.argv[1:]
    sys.exit(subprocess.run(cmd).returncode)

if __name__ == "__main__":
    main()
