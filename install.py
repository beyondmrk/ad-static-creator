"""One-command install and update for ad-static-creator. Safe to re-run any time.

  python install.py                  # both engines
  python install.py --engine flow    # or higgsfield

It installs and configures everything a job needs. Only the sign-ins stay with the person: Google
in the Flow window it opens, Higgsfield in the browser. It ends with `adloc.py doctor`, and exits
non-zero while anything is still missing.
"""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLOW = Path(os.environ.get("FLOW_MCP_DIR", HERE / "flow-mcp"))
FLOW_REPO = "https://github.com/beyondmrk/flow-mcp"
JOBS = Path.home() / "ad-static-jobs"
EDGE = [Path(os.environ.get(v, "")) / "Microsoft/Edge/Application/msedge.exe"
        for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]


def run(*cmd, cwd=None, check=True):
    print("  $", " ".join(map(str, cmd)), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd)
    if check and r.returncode:
        sys.exit(f"install stopped: `{cmd[0]} {cmd[1] if len(cmd) > 1 else ''}` failed (exit {r.returncode})")
    return r.returncode


def refresh_path():
    """Pick up what winget just installed without a new terminal."""
    if os.name != "nt":
        return
    import winreg
    parts = []
    for root, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(root, key) as k:
                parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
        except OSError:
            pass
    os.environ["PATH"] = ";".join(parts + [os.environ["PATH"]])


def need(exe, winget_id):
    if shutil.which(exe):
        return
    if os.name == "nt" and shutil.which("winget"):
        run("winget", "install", "-e", "--id", winget_id, "--silent",
            "--accept-package-agreements", "--accept-source-agreements", check=False)
        refresh_path()
    if not shutil.which(exe):
        sys.exit(f"install stopped: {exe} is missing and could not be installed - install it, then re-run")


def update_code():
    print("code:")
    if (HERE / ".git").exists():
        run("git", "-C", HERE, "pull", "--ff-only", check=False)  # local edits: keep them, skip the update
        run("git", "-C", HERE, "submodule", "update", "--init", "--recursive")
    elif not (FLOW / "pyproject.toml").exists():
        run("git", "clone", FLOW_REPO, FLOW)
    run(sys.executable, "-m", "pip", "install", "-q", "-r", HERE / "requirements.txt")


def install_flow():
    print("flow:")
    if os.name != "nt":
        print("  the Flow bridge runs on Windows only (Edge) - skipped")
        return
    if not shutil.which("uv"):
        run(sys.executable, "-m", "pip", "install", "-q", "uv")
        refresh_path()
    uv = shutil.which("uv") or [sys.executable, "-m", "uv"]
    run(*([uv] if isinstance(uv, str) else uv), "sync", "-q", cwd=FLOW)
    cfg = FLOW / "config.toml"
    if not cfg.exists():
        JOBS.mkdir(parents=True, exist_ok=True)
        edge = next((p for p in EDGE if p.is_file()), None)
        text = (FLOW / "config.example.toml").read_text(encoding="utf-8")
        text = text.replace('work_root = "C:\\\\flow-projects"', f"work_root = {json.dumps(str(JOBS))}")
        if edge:
            text = "\n".join(f"edge_exe = {json.dumps(str(edge))}" if l.startswith("edge_exe") else l
                             for l in text.splitlines()) + "\n"
        cfg.write_text(text, encoding="utf-8")
        print(f"  wrote {cfg} (jobs go in {JOBS})")
    claude = shutil.which("claude")
    if not claude:
        print("  Claude Code CLI not on PATH - the flow MCP tools (flow_sweep) are not registered")
    elif subprocess.run([claude, "mcp", "get", "flow"], capture_output=True).returncode:
        run(claude, "mcp", "add", "--scope", "user", "flow", "--", "uv", "--directory", FLOW, "run", "flow-mcp")
    print("  opening the Flow window: sign in to Google there if it asks (once per machine)")
    run(*([uv] if isinstance(uv, str) else uv), "run", "--directory", FLOW, "python", "-c",
        "import sys; sys.path.insert(0, 'src'); from flow_mcp.service import Service; "
        "s = Service.build().status(); print('  Flow signed in:', s.get('signed_in'), ' captcha:', s.get('captcha'))",
        check=False)


def install_higgsfield():
    print("higgsfield:")
    import hf
    if subprocess.run([hf.HF, "version"], capture_output=True).returncode:
        need("npm", "OpenJS.NodeJS.LTS")
        # npm blocks the postinstall that downloads the real binary unless it is allowed by name
        run(shutil.which("npm"), "install", "-g", "--allow-scripts=@higgsfield/cli", "@higgsfield/cli")
        refresh_path()
        import importlib
        importlib.reload(hf)
        run(hf.HF, "version")
    logins = [p for p in hf.LOGINS.iterdir() if p.is_dir() and hf.NAME_RE.match(p.name)] \
        if hf.LOGINS.is_dir() else []
    if logins:
        print("  logins:", ", ".join(p.name for p in logins), " (add more: python hf.py add <name>)")
    elif sys.stdin.isatty():
        name = input("  Name your first Higgsfield login (lowercase, e.g. team): ").strip().lower()
        if name:
            run(sys.executable, HERE / "hf.py", "add", name, check=False)
    else:
        print("  no Higgsfield login yet: python hf.py add <name>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["flow", "higgsfield"], help="default: both")
    a = ap.parse_args()
    if sys.version_info < (3, 11):
        sys.exit("Python 3.11 or newer is needed")
    update_code()
    if a.engine in (None, "flow"):
        install_flow()
    if a.engine in (None, "higgsfield"):
        install_higgsfield()
    print("check:")
    sys.exit(subprocess.run([sys.executable, HERE / "adloc.py", "doctor"]
                            + (["--engine", a.engine] if a.engine else [])).returncode)


if __name__ == "__main__":
    main()
