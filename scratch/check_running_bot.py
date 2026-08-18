import subprocess
import sys
import os

def main():
    print("Listing python processes...")
    try:
        # Use wmic to get commandline and processid
        out = subprocess.check_output('wmic process where "name=\'python.exe\'" get CommandLine, ProcessID', shell=True)
        print(out.decode('cp1251', errors='replace'))
    except Exception as e:
        print(f"Error running wmic: {e}")
        
    try:
        # Also try powershell with CimInstance
        cmd = 'powershell -Command "Get-CimInstance Win32_Process -Filter \\"name = \'python.exe\'\\" | Select-Object ProcessId, CommandLine | Format-Table -Wrap"'
        out_ps = subprocess.check_output(cmd, shell=True)
        print("Powershell output:")
        print(out_ps.decode('cp1251', errors='replace'))
    except Exception as e:
        print(f"Error running powershell: {e}")

if __name__ == "__main__":
    main()
