import subprocess
import sys
import os

def main():
    try:
        # Change to src directory and run main.py
        os.chdir('src')
        result = subprocess.run([sys.executable, 'main.py'])
        return result.returncode
    except KeyboardInterrupt:
        print("\n Bot stopped by user")
        return 0
    except Exception as e:
        print(f"\nError running bot: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
