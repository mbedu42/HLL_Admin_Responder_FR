import argparse, os, subprocess, sys, time, shutil, stat, signal
from pathlib import Path

def sh(cmd, check=True, cwd=None, env=None, capture=False):
    p = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        check=check,
        text=True,
        capture_output=capture,
        shell=True,
    )
    return p.stdout if capture else None

def which(x): return shutil.which(x) is not None
def die(msg): print(f"ERR: {msg}", file=sys.stderr); sys.exit(1)
def log(msg): print(msg, flush=True)

def ensure_tmp_perms():
    try:
        m = oct(stat.S_IMODE(os.stat("/tmp").st_mode))
        if m != "0o1777":
            log("WARN: /tmp not 1777; attempting fix")
            sh("chmod 1777 /tmp", check=False)
    except Exception:
        pass

def git_update(dir_path: Path, branch: str):
    if not (dir_path / ".git").exists():
        die(f"{dir_path} is not a git repo")
    sh("git fetch --all -q", cwd=dir_path)
    sh(f"git reset --hard origin/{branch}", cwd=dir_path)
    rev = sh("git rev-parse --short HEAD", cwd=dir_path, capture=True).strip()
    log(f"git @ {branch} -> {rev}")

def ensure_venv(dir_path: Path):
    venv_dir = dir_path / "venv"
    venv_py = venv_dir / "bin" / "python"
    if not venv_py.exists():
        sh(f"python3 -m venv {venv_dir}")
    sh(f"{venv_py} -V")
    sh(f"{venv_py} -m pip install -U pip")
    sh(f"{venv_py} -m pip install -r requirements.txt", cwd=dir_path)
    return venv_py

def check_env(dir_path: Path):
    envfile = dir_path / ".env"
    if not envfile.exists():
        die(".env missing")
    text = envfile.read_text()
    if "DISCORD_TOKEN=" not in text:
        die("DISCORD_TOKEN missing in .env")
    return True

def tmux(cmd: str, socket: str):
    return sh(f"tmux -L {socket} {cmd}", check=False)

def iter_bot_pids(dir_path: Path):
    """
    Return PIDs of python run.py processes belonging to this project.
    Uses pgrep + /proc/<pid>/cwd so it sees all of them, detached or not.
    """
    out = sh("pgrep -af 'python.*run.py'", capture=True, check=False)
    if not out:
        return
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if not parts[0].isdigit():
            continue
        pid = int(parts[0])
        if pid == os.getpid():
            continue
        # verify cwd matches project or cmdline contains project path
        cwd = None
        try:
            cwd = Path(f"/proc/{pid}/cwd").resolve()
        except FileNotFoundError:
            continue
        if cwd == dir_path or str(dir_path) in line:
            yield pid

def kill_existing_instances(dir_path: Path, session: str, socket: str):
    os.environ.pop("TMUX", None)

    # Kill tmux session for this bot
    tmux(f"kill-session -t {session}", socket)

    def kill_with(sig):
        for pid in list(iter_bot_pids(dir_path)):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass

    # soft
    kill_with(signal.SIGTERM)
    time.sleep(1)

    # hard if needed
    remaining = list(iter_bot_pids(dir_path))
    if remaining:
        kill_with(signal.SIGKILL)
        time.sleep(0.5)

    # report how many are left (for your sanity)
    left = list(iter_bot_pids(dir_path))
    if left:
        log(f"WARN: still running after cleanup: {left}")
    else:
        log("OK: no existing bot processes for this project")

def start_detached(dir_path: Path, venv_py: Path, session: str, socket: str):
    if not which("tmux"):
        die("tmux not installed for -d mode")

    ensure_tmp_perms()
    kill_existing_instances(dir_path, session, socket)

    sh(f"tmux -L {socket} start-server")
    sh(f"tmux -L {socket} new-session -d -s {session} -c {dir_path}")
    logdir = dir_path / "logs"
    logdir.mkdir(exist_ok=True)
    tmux(
        f"pipe-pane -o -t {session} \"cat >> '{(logdir / f'tmux-{session}.log')}'\"",
        socket,
    )

    cmd = f"source {dir_path/'venv/bin/activate'} && exec {venv_py} run.py"
    tmux(f"send-keys -t {session} \"{cmd}\" C-m", socket)

    ok = False
    for _ in range(12):
        time.sleep(1)
        if list(iter_bot_pids(dir_path)):
            ok = True
            break

    out = sh(f"tmux -L {socket} ls", check=False, capture=True) or ""
    if not ok or session not in out:
        die("tmux session not found or bot not running after start")

    log(f"OK: running in background. Attach: tmux -L {socket} attach -t {session}")
    log(f"Logs: tail -f {logdir / f'tmux-{session}.log'}")

def start_foreground(dir_path: Path, venv_py: Path, session: str, socket: str):
    kill_existing_instances(dir_path, session, socket)

    os.chdir(dir_path)
    log("Starting foreground. Ctrl-C to stop.")
    p = subprocess.Popen([str(venv_py), "run.py"], cwd=dir_path)
    try:
        p.wait()
    except KeyboardInterrupt:
        try:
            p.terminate()
        except ProcessLookupError:
            pass
        p.wait()
    sys.exit(p.returncode)

def preflight_compile(dir_path: Path, venv_py: Path):
    src_dir = dir_path / "src"
    if not src_dir.exists():
        return
    cmd = f"""{venv_py} - <<'PY'
import compileall, sys
ok = compileall.compile_dir(r'''{src_dir}''', quiet=1)
sys.exit(0 if ok else 1)
PY"""
    r = subprocess.run(cmd, shell=True)
    if r.returncode != 0:
        die("Syntax error detected during compile step. Fix Python files in src/ and retry.")

def main():
    ap = argparse.ArgumentParser(description="Start HLL Admin Responder")
    ap.add_argument("-d", "--detached", action="store_true", help="run in background via tmux")
    ap.add_argument("--dir", default=str(Path.home() / "HLL_Admin_Responder_FR"))
    ap.add_argument("--branch", default="main")
    ap.add_argument("--session", default="hll-admin")
    ap.add_argument("--socket", default="hll")
    args = ap.parse_args()

    dir_path = Path(args.dir).expanduser().resolve()
    if not dir_path.exists():
        die(f"dir not found: {dir_path}")

    log(f"dir: {dir_path}")
    log(f"branch: {args.branch}")

    git_update(dir_path, args.branch)
    check_env(dir_path)
    venv_py = ensure_venv(dir_path)
    preflight_compile(dir_path, venv_py)

    (dir_path / "logs").mkdir(exist_ok=True)

    if args.detached:
        start_detached(dir_path, venv_py, args.session, args.socket)
    else:
        start_foreground(dir_path, venv_py, args.session, args.socket)

if __name__ == "__main__":
    main()
