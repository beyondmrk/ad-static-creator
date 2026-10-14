"""Flow engine for ad-static-creator: recreate every line of prompts.json in Google Flow through the
flow-mcp bridge (the flow-mcp submodule, or $FLOW_MCP_DIR). Runs in the bridge's environment:

  uv run --directory flow-mcp python ../flow_run.py <job> [--only 03 07] [--reroll]

One still per line, fired one at a time, downloaded to <job>/Elements/Stills as it lands.
A line that already has a still is skipped; --reroll adds an _altN take, it never replaces one.
UNCONFIRMED stops the run: run flow_sweep, never re-fire.
"""
import argparse, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(os.environ.get("FLOW_MCP_DIR", HERE / "flow-mcp")) / "src"))
from flow_mcp.guards import FlowError  # noqa: E402
from flow_mcp.service import Service  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--reroll", action="store_true")
    a = ap.parse_args()
    job = Path(a.job).resolve()
    P = json.loads((job / "prompts.json").read_text(encoding="utf-8"))
    if P.get("engine", "flow") != "flow":
        sys.exit("this job's engine is higgsfield - fire it with hf.py")
    stills = job / "Elements" / "Stills"
    only = {o.zfill(2) for o in a.only}
    lines = [l for l in P["lines"] if (not only or l["line"] in only)
             and (a.reroll or not list(stills.glob(f"claude_{P['slug']}_line{l['line']}*.png")))]
    if not lines:
        sys.exit("nothing to fire (every selected line has a still; --reroll adds a take)")
    svc = Service.build()
    st = svc.status()
    if not st.get("signed_in") or st.get("captcha"):
        sys.exit(f"Flow is not ready (signed_in={st.get('signed_in')}, captcha={st.get('captcha')}) - "
                 "the user fixes it in the bridge's Edge window")
    try:
        svc.open_project(P["slug"].upper(), job)
        up = svc.upload_many(sorted({r for l in lines for r in l["refs"]}), job)
        if up["errors"]:
            sys.exit(f"upload refused: {up['errors']}")
        for l in lines:
            out = svc.fire_still(job, P["slug"], l["line"], l["prompt"], refs=l["refs"],
                                 aspect=l["aspect"], reroll=a.reroll)
            if out["status"] == "UNCONFIRMED":
                sys.exit(f"  {l['line']}: UNCONFIRMED - run flow_sweep, never re-fire it")
            if out["status"] != "committed":
                print(f"  {l['line']}: {out['status']} {out.get('detail', '')}", flush=True)
                continue
            dl = svc.download(job, out["media_ids"])
            print(f"  {l['line']}: {', '.join(map(str, dl.get('written', []))) or dl}", flush=True)
    except FlowError as e:  # browser, login, captcha, UI: every later line would hit it too
        sys.exit(f"stopped: {e.code} {e}")
    print("done - next: python adloc.py finish <job>")


if __name__ == "__main__":
    main()
