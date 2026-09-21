"""Universal Launcher for LostWeapon Physics Playground."""
import os
import subprocess
import sys
from pathlib import Path

def main():
    base_dir = Path(__file__).resolve().parent
    harness_dir = base_dir / "native_harness"
    script = harness_dir / "native_playground.py"
    
    if not script.is_file():
        # If launcher is running from Desktop, search for the project folder on Desktop
        desktop = Path.home() / "Desktop"
        for item in desktop.iterdir():
            if item.is_dir():
                cand = item / "native_harness" / "native_playground.py"
                if cand.is_file():
                    harness_dir = cand.parent
                    script = cand
                    break
                
    if not script.is_file():
        print(f"[ERROR] Cannot locate native_harness/native_playground.py from {base_dir}")
        input("Press Enter to exit...")
        sys.exit(1)
        
    print("=======================================================")
    print("  LostWeapon Native Physics Playground Launcher")
    print("=======================================================")
    print(f"[1/2] Harness location: {harness_dir}")
    print("[2/2] Opening simulator window. Please wait...")
    
    # Run the playground
    returncode = subprocess.call([sys.executable, str(script)], cwd=str(harness_dir))
    if returncode != 0:
        print(f"\n[ERROR] Simulator exited with return code {returncode}")
        input("Press Enter to exit...")
        sys.exit(returncode)

if __name__ == "__main__":
    main()
