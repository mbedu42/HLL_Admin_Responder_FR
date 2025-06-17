import subprocess
import sys
import os

# Change to src directory and run main.py
os.chdir('src')
subprocess.run([sys.executable, 'main.py'])