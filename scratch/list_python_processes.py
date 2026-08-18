import subprocess
try:
    res = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessID,CommandLine'], capture_output=True, text=True, errors='ignore')
    print(res.stdout)
except Exception as e:
    print(e)
