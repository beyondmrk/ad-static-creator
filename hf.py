"""Higgsfield engine for ad-static-creator: several Higgsfield logins side by side, and the fire.

Each login is its own folder under ~/.hf-logins (or $HF_LOGINS). The CLI runs with HOME and
USERPROFILE pointed at that folder, so every login keeps its own session and selected workspace,
and a job can only fire on the login + workspace its brief names. This script never signs in,
signs out or selects a workspace: those stay with the user.

  python hf.py add <name>                     # make a login folder, print how to sign it in
  python hf.py status [<name>]                # email, workspace and credits of every login
  python hf.py fire <job> [--only 03 07] [--reroll] [--resolution 2k]          # quote only
  python hf.py fire <job> ... --yes           # spend: the user said fire
"""
import argparse, json, os, re, shutil, subprocess, sys, urllib.request
from pathlib import Path

LOGINS = Path(os.environ.get("HF_LOGINS") or Path.home() / ".hf-logins")
# npm's higgsfield.cmd shim goes through cmd.exe, which cuts a command line at the first newline;
# the vendored exe takes the prompt whole
_VENDOR = Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@higgsfield/cli/vendor/hf.exe"
HF = str(_VENDOR) if os.name == "nt" and _VENDOR.is_file() else (shutil.which("higgsfield") or "higgsfield")
MODEL = "nano_banana_2"  # Higgsfield's id for Nano Banana Pro
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def env_for(name):
    d = LOGINS / name
    if not NAME_RE.match(name or "") or not d.is_dir():
        sys.exit(f"no login {name!r} under {LOGINS} - python hf.py add {name}")
    return dict(os.environ, HOME=str(d), USERPROFILE=str(d), HF_CLIENT=name)


def call(name, *args, timeout=120):
    """(parsed JSON or None, error text) of one CLI call on login `name`."""
    r = subprocess.run([HF, *args, "--json"], env=env_for(name), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    try:
        return json.loads(r.stdout), ""
    except ValueError:
        return None, " ".join((r.stderr or r.stdout or f"exit {r.returncode}").split())[-300:]


def whoami(name):
    acct, err = call(name, "account", "status")
    ws, err2 = call(name, "workspace", "status")
    return acct, ws, err or err2


def check(name, want):
    """'' when login `name` is signed in on workspace `want` (its id or name), else what is wrong."""
    acct, ws, err = whoami(name)
    if not acct or not ws:
        return f"login {name} is not signed in or not readable ({err}) - python hf.py add {name}"
    if want not in (ws.get("id"), ws.get("name")):
        return (f"login {name} is on workspace {ws.get('name') or ws.get('id')}, the brief wants {want} - "
                "select it yourself with this login (higgsfield workspace set <id>)")
    return ""


def next_name(stills, slug, line):
    """Flow's naming (claude_<slug>_lineNN[_altK].png), so finish reads both engines; never overwrites."""
    base = f"claude_{slug}_line{line}"
    if not (stills / f"{base}.png").exists():
        return stills / f"{base}.png"
    k = 2
    while (stills / f"{base}_alt{k}.png").exists():
        k += 1
    return stills / f"{base}_alt{k}.png"


def cmd_add(a):
    if not NAME_RE.match(a.name):
        sys.exit("login names: lowercase letters, digits, - and _ (start with a letter or digit)")
    d = LOGINS / a.name
    d.mkdir(parents=True, exist_ok=True)
    print(f"login folder: {d}\nSign it in yourself, in a NEW terminal window:")
    if os.name == "nt":
        print(f'  $env:HOME="{d}"; $env:USERPROFILE="{d}"\n  higgsfield auth login\n'
              "  higgsfield workspace list\n  higgsfield workspace set <id>")
    else:
        print(f'  export HOME="{d}"\n  higgsfield auth login\n  higgsfield workspace list\n'
              "  higgsfield workspace set <id>")
    print(f"Close that window, then check: python hf.py status {a.name}")


def cmd_status(a):
    names = [a.name] if a.name else sorted(
        p.name for p in (LOGINS.iterdir() if LOGINS.is_dir() else []) if p.is_dir() and NAME_RE.match(p.name))
    if not names:
        print(f"no logins under {LOGINS} - python hf.py add <name>")
    for n in names:
        acct, ws, err = whoami(n)
        if acct and ws:
            print(f"  {n:12} {acct.get('email')}  workspace {ws.get('name') or '-'} ({ws.get('id')})  "
                  f"{ws.get('credits', acct.get('credits')) or 0:.1f} credits")
        else:
            print(f"  {n:12} NOT READY: {err}")


def cmd_fire(a):
    job = Path(a.job).resolve()
    brief = json.loads((job / "brief.json").read_text(encoding="utf-8"))
    P = json.loads((job / "prompts.json").read_text(encoding="utf-8"))
    if P.get("engine") != "higgsfield":
        sys.exit("this job's engine is flow - fire it with flow_run.py")
    login = brief["hf_login"]
    problem = check(login, brief["hf_workspace"])
    if problem:
        sys.exit(f"fire refused: {problem}")
    stills = job / "Elements" / "Stills"
    stills.mkdir(parents=True, exist_ok=True)
    only = {o.zfill(2) for o in a.only}
    lines = [l for l in P["lines"] if not only or l["line"] in only]
    todo = [l for l in lines if a.reroll or not list(stills.glob(f"claude_{P['slug']}_line{l['line']}*.png"))]
    each = (call(login, "generate", "cost", MODEL, "--prompt", "x", "--resolution", a.resolution)[0] or {}).get("credits")
    acct, _ = call(login, "account", "status")
    have = (acct or {}).get("credits") or 0
    total = each * len(todo) if each is not None else None
    print(f"{len(todo)} stills, {MODEL} {a.resolution}, login {login} ({(acct or {}).get('email')}): "
          f"{each} credits each, {total} total, {have:.1f} available"
          + (f"; {len(lines) - len(todo)} already have a still (--reroll adds a take)" if len(todo) < len(lines) else ""))
    if not a.yes or not todo:
        print("Nothing fired." + (" Re-run with --yes once the user says fire." if todo else ""))
        return
    if total is not None and total > have:
        sys.exit(f"not enough credits: {total} needed, {have:.1f} available")
    shim = not HF.lower().endswith(".exe") and os.name == "nt"
    for l in todo:
        prompt = " ".join(l["prompt"].split("\n")) if shim else l["prompt"]
        cmd = ["generate", "create", MODEL, "--prompt", prompt, "--aspect_ratio", l["aspect"],
               "--resolution", a.resolution, "--wait", "--wait-timeout", "15m"]
        for r in l["refs"]:
            cmd += ["--image-references", r]
        out, err = call(login, *cmd, timeout=1000)
        j = out[0] if isinstance(out, list) and out else out if isinstance(out, dict) else {}
        url = j.get("result_url")
        if not url:
            sys.exit(f"  {l['line']}: no result ({err or out}). The job may still be running or paid: "
                     "check `higgsfield generate list` on this login before firing it again.")
        dst = next_name(stills, P["slug"], l["line"])
        tmp = dst.with_suffix(".part")
        tmp.write_bytes(urllib.request.urlopen(url, timeout=120).read())
        tmp.rename(dst)
        print(f"  {l['line']}: {dst.name}  {url}", flush=True)  # each result shows as it lands
    print("done - next: python adloc.py finish <job>")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add"); p.add_argument("name")
    p = sub.add_parser("status"); p.add_argument("name", nargs="?")
    p = sub.add_parser("fire"); p.add_argument("job")
    p.add_argument("--only", nargs="*", default=[]); p.add_argument("--reroll", action="store_true")
    p.add_argument("--resolution", default="2k", choices=["1k", "2k", "4k"])
    p.add_argument("--yes", action="store_true", help="the user confirmed the quote: spend")
    a = ap.parse_args()
    {"add": cmd_add, "status": cmd_status, "fire": cmd_fire}[a.cmd](a)


if __name__ == "__main__":
    main()
