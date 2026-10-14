"""ad-static-creator: competitor static ads recreated 1:1 for our product, optionally localized.

  python adloc.py init    <job> --code AB-12 --product "Name" [--lang Dutch --market Netherlands]
                                [--engine flow|higgsfield] [--hf-login NAME --hf-workspace ID]
                                [--product-image p.png] [--competitor "Brand"]
                                [--currency € --price "€39,95" --offer "..." --guarantee "..."]
                                [--profile profiles/daily-12.json]
  python adloc.py fetch   <job> <urls.json>      # -> 01_originals + sources.json + links file
  python adloc.py scan    <job>                  # set rules + dedupe + ads.json skeleton
  python adloc.py build   <job> [--spell 03] [--allow-short]
  python hf.py fire <job>  |  uv run --directory flow-mcp python ../flow_run.py <job>
  python adloc.py finish  <job> [--pick 03=alt2] # stills -> crop -> 02_localized + text check
  python adloc.py review  <job>                  # original | ours, one side-by-side sheet
  python adloc.py deliver <job> [--set 1 --start 1] [--only 03 --suffix v2] [--upload "remote:dir"]
  python adloc.py doctor  [<job>]                # setup check

No --lang = 1:1 mode: the text stays in the original language; only our product, brand, price,
offer, guarantee and market references change. Flow jobs must sit under flow-mcp's work_root
(set FLOW_WORK_ROOT to it and `init` enforces it).
The prompt is ASSEMBLED here from ads.json; nobody hand-writes a generation prompt.
"""
import argparse, difflib, json, math, os, re, shutil, subprocess, sys, unicodedata
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from clean import IMG, VID, clean, leftovers

HERE = Path(__file__).resolve().parent
ASPECTS = {"flow": ("1:1", "3:4", "4:3", "9:16", "16:9"),
           "higgsfield": ("1:1", "3:2", "2:3", "4:3", "3:4", "4:5", "5:4", "9:16", "16:9", "21:9")}
DUP_BITS = 70  # dHash Hamming distance (of 256) at or below = same creative
DEFAULT_PROFILE = {"set_size": 0, "provided_min": 0, "min_reach": 0, "require_niche_note": False,
                   "delivery_pattern": "{code}-S{set}-A{n}", "status_value": "", "notify_template": ""}
# money, discounts and bundle maths: a text block like this is an OFFER claim, never plain copy
OFFER_RE = re.compile(r"[$€£¥]|\d+[.,]\d{2}\b|\d+\s?%|\b(kr|zł|sek|eur|usd|dkk|nok|pln|chf|gbp)\b"
                      r"|\b\d+\s*\+\s*\d+\b|\bgratis\b|\bfree\b|\bgratuit|\bkostenlos|\bomaggio"
                      r"|garanti|guarantee|money.?back|geld.?(zur|terug)|rimborso|rembours"
                      r"|\b(buy|kaufe?|koop|köp|kup|achetez|compra)\b", re.I)
KINDS = {"copy", "brand", "price", "offer", "guarantee", "country"}
NEEDS = {"price": ("price", "currency"), "offer": ("offer",), "guarantee": ("guarantee",),
         "country": ("market",)}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def natural(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def nums(s):
    return re.findall(r"\d+", re.sub(r"(?<=\d)[.,\s](?=\d)", "", s))


def profile(job, brief):
    p = dict(DEFAULT_PROFILE)
    if brief.get("profile"):
        path = Path(brief["profile"])
        p.update(load(path if path.is_absolute() else HERE / path))
    return p


def originals(job):
    return sorted((p for p in (job / "01_originals").iterdir()
                   if p.suffix.lower() in IMG and not p.stem.startswith("product")), key=natural)


def ratio(aspect):
    w, h = aspect.split(":")
    return int(w) / int(h)


def pick_aspect(w, h, engine):
    r = w / h
    name = min(ASPECTS[engine], key=lambda k: abs(math.log(ratio(k) / r)))
    return name, abs(ratio(name) / r - 1) > 0.02  # (aspect, needs pad/crop)


def newest(s):
    """The newest take of a localized ad: s itself or its highest _vN sibling."""
    takes = [s] + [p for p in s.parent.glob(f"{s.stem}_v*{s.suffix}")
                   if re.fullmatch(rf"{re.escape(s.stem)}_v\d+", p.stem)]
    return max(takes, key=lambda p: int(re.search(r"_v(\d+)$", p.stem).group(1)) if p is not s else 1)


def dhash(path):
    im = Image.open(path).convert("L").resize((17, 16), Image.LANCZOS)
    px = list(im.tobytes())
    return [px[r * 17 + c] > px[r * 17 + c + 1] for r in range(16) for c in range(16)]


# ---------------------------------------------------------------------------- init / fetch / scan
def cmd_init(a):
    job = Path(a.job).resolve()
    root = os.environ.get("FLOW_WORK_ROOT")
    if a.engine == "flow":
        if root and not job.is_relative_to(Path(root).resolve()):
            sys.exit(f"job folder must live under FLOW_WORK_ROOT ({root}), flow-mcp's path fence")
        if not root:
            print("NOTE: FLOW_WORK_ROOT not set - make sure the job sits under flow-mcp's work_root")
    elif not (a.hf_login and a.hf_workspace):
        sys.exit("--engine higgsfield needs --hf-login and --hf-workspace (python hf.py status lists them)")
    if (job / "brief.json").exists():
        sys.exit(f"brief.json already exists in {job} - edit it, never re-init")
    for d in ("01_originals", "02_localized", "03_delivery", "Elements/Stills", "Elements/_refs"):
        (job / d).mkdir(parents=True, exist_ok=True)
    brief = {"code": a.code.upper(), "lang": a.lang or "", "market": a.market or "",
             "engine": a.engine, "hf_login": a.hf_login or "", "hf_workspace": a.hf_workspace or "",
             "product": a.product, "competitor": a.competitor or "", "product_image": "",
             "currency": a.currency or "", "price": a.price or "", "offer": a.offer or "",
             "guarantee": a.guarantee or "", "profile": a.profile or ""}
    if a.profile:
        profile(job, brief)  # fail now on a bad profile path, not at delivery
    if a.product_image:
        src = Path(a.product_image)
        dst = job / "01_originals" / f"product{src.suffix.lower()}"
        shutil.copy2(src, dst)
        brief["product_image"] = dst.name
    save(job / "brief.json", brief)
    print(f"job ready: {job}  ({a.engine}, "
          + (f"localized to {a.lang})" if a.lang else "1:1 in the original language)"))


def cmd_fetch(a):
    """urls.json: {"01_<adid>": "<cdn url>"} or {"01_<adid>": {"url", "origin", "reach", "niche"}}.
    origin = provided (came with the brief) | researched (found by us)."""
    job = Path(a.job)
    src_path = job / "sources.json"
    sources = load(src_path) if src_path.exists() else {}
    for name, v in load(a.urls).items():
        v = {"url": v} if isinstance(v, str) else v
        adid = name.split("_", 1)[1] if "_" in name else name
        sources[name] = {"link": v.get("link") or f"https://www.facebook.com/ads/library/?id={adid}",
                         "origin": v.get("origin", "provided"), "reach": v.get("reach"),
                         "niche": v.get("niche", "")}
        ext = ".png" if ".png" in v["url"].split("?")[0] else ".jpg"
        dst = job / "01_originals" / f"{name}{ext}"
        if dst.exists():
            print(f"  have {dst.name}")
            continue
        req = urllib.request.Request(v["url"], headers={"User-Agent": "Mozilla/5.0"})
        dst.write_bytes(urllib.request.urlopen(req, timeout=60).read())
        print(f"  got  {dst.name}  {Image.open(dst).size}")
    save(src_path, sources)
    (job / "competitor_ad_links.txt").write_text(
        "".join(f"{n}\t{s['origin']}\t{s['link']}\n" for n, s in sorted(sources.items())),
        encoding="utf-8", newline="\n")


def set_problems(job, brief):
    """The team's set rules (profile): size, provided minimum, reach floor, niche note, links."""
    prof = profile(job, brief)
    srcs = load(job / "sources.json") if (job / "sources.json").exists() else {}
    names = [f.stem for f in originals(job)]
    errs = [f"{n}: no source entry (fetch it, or add it to sources.json)" for n in names
            if n not in srcs]
    used = [srcs[n] for n in names if n in srcs]
    if prof["set_size"] and len(names) != prof["set_size"]:
        errs.append(f"set has {len(names)} ads, the profile wants {prof['set_size']}")
    prov = sum(s["origin"] == "provided" for s in used)
    if prof["provided_min"] and prov < prof["provided_min"]:
        errs.append(f"only {prov} provided ads, the profile expects at least {prof['provided_min']}")
    for n in names:
        s = srcs.get(n)
        if not s or s["origin"] != "researched":
            continue
        if prof["min_reach"] and not (s.get("reach") or 0) > prof["min_reach"]:
            errs.append(f"{n}: researched ad reach {s.get('reach')} - must be over {prof['min_reach']}")
        if prof["require_niche_note"] and not s.get("niche", "").strip():
            errs.append(f"{n}: researched ad needs a niche note (same product, or same problem/audience)")
    return errs


def cmd_scan(a):
    job = Path(a.job)
    brief = load(job / "brief.json")
    files = originals(job)
    hashes = {f.name: dhash(f) for f in files}
    dups = []
    for i, f in enumerate(files):
        for g in files[:i]:
            d = sum(x != y for x, y in zip(hashes[f.name], hashes[g.name]))
            if d <= DUP_BITS:
                dups.append((f.name, g.name, d))
    path = job / "ads.json"
    ads = load(path) if path.exists() else {}
    for f in files:
        w, h = Image.open(f).size
        asp, pad = pick_aspect(w, h, brief.get("engine", "flow"))
        ads.setdefault(f.name, {"size": [w, h], "aspect": asp, "padded": pad,
                                "has_text": None, "has_product": None, "scene": "",
                                "texts": [], "swaps": []})
    save(path, ads)
    print(f"{len(files)} originals -> {path.name}")
    for f in files:
        e = ads[f.name]
        print(f"  {f.name:32} {e['size'][0]}x{e['size'][1]}  {brief.get('engine', 'flow')} {e['aspect']}"
              + ("  (pad + crop back)" if e["padded"] else ""))
    for f, g, d in dups:
        print(f"  DUPLICATE? {f} ~ {g} (dHash {d}/256) - replace one before build")
    for p in set_problems(job, brief):
        print(f"  SET: {p}")


# ---------------------------------------------------------------------------- build
def pad_ref(src, dst, asp):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    r = ratio(asp)
    W, H = (w, round(w / r)) if r < w / h else (round(h * r), h)
    bg = im.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(max(W, H) // 25))
    bg.paste(im, ((W - w) // 2, (H - h) // 2))
    bg.save(dst)
    return "top and bottom" if H > h else "left and right"


def spelled(text):
    words = sorted({w for w in re.findall(r"\w+", text) if len(w) > 3 and not w.isdigit()})
    return "; ".join(f'"{w}" = {"-".join(w)}' for w in words)


def prompt_for(e, brief, bands, spell):
    lang, prod = brief["lang"], brief["product"]
    out = [e["scene"].strip()]
    changes = []
    if e["has_text"]:
        out.append(f"On-image text, in {lang or 'the same language as the original'}, each in the same "
                   "position, size, colour and font as the original:")
        out += [f'- {t["where"]}: "{t["target"]}"' for t in e["texts"]]
        if lang:
            changes.append(f"the text (now native {lang}, exactly as listed)")
        elif any(t["target"] != t["source"] for t in e["texts"]):
            changes.append("the text (exactly as listed)")
    for s in e.get("swaps", []):
        out.append(f"Replace {s['from']} with {s['to']}.")
    if e.get("swaps"):
        changes.append("the listed replacements")
    if e["has_product"]:
        out.append(f"The second reference image is our product, {prod}. Replace the competitor's "
                   "product with it at the same position, size and angle, keeping its packaging "
                   "and label exactly as in the second reference image."
                   + (f" Every product name in the ad reads {prod}." if e["has_text"] else ""))
        changes.append("the product")
    if changes:
        listed = changes[0] if len(changes) == 1 else ", ".join(changes[:-1]) + " and " + changes[-1]
        out.append("Copy the first reference image 1:1. Change only " + listed + ". "
                   "Keep the layout, people, colours, lighting, crop and typography identical.")
    else:
        out.append("Copy the first reference image 1:1. Keep it identical: same subject, "
                   "composition, framing, colours and lighting.")
    if e["has_text"]:
        out.append("Spell every word and every number exactly as written above, with "
                   + (f"correct {lang} characters." if lang else "the original's characters and accents."))
        if spell:
            out.append("Spelling, letter by letter: "
                       + spelled(" ".join(t["target"] for t in e["texts"])) + ".")
    else:
        out.append("The original image contains no text, so add no text, letters, words, "
                   "captions, labels or watermarks anywhere.")
    if bands:
        out.append(f"The first reference image has blurred padding bands at the {bands}. Extend the "
                   f"scene naturally into those bands and keep the whole ad inside the centre area "
                   f"exactly as it is.")
    return "\n".join(out)


def competitors(brief, e=None):
    """Every competitor brand to keep out: brief.competitor (comma-separated) + the ad's own."""
    names = brief["competitor"].split(",") + ((e or {}).get("competitor") or "").split(",")
    return [n.strip().lower() for n in names if n.strip()]


def ad_problems(name, e, brief):
    errs = []
    comps = competitors(brief, e)
    if e["has_text"] is None or e["has_product"] is None:
        errs.append(f"{name}: has_text / has_product not set")
    if not e["scene"].strip():
        errs.append(f"{name}: scene is empty (describe the original as it is)")
    if e["has_text"] and not e["texts"]:
        errs.append(f"{name}: has_text but no texts")
    ours = [n for k in ("price", "offer", "guarantee") for n in nums(brief[k])]  # per field: a join would merge "29,95 2+1"
    for t in e["texts"]:
        kind = t.get("kind", "copy")
        if not t.get("source", "").strip() or not t.get("target", "").strip() or not t.get("where"):
            errs.append(f"{name}: text entry needs source, target and where: {t}")
            continue
        if kind not in KINDS:
            errs.append(f"{name}: kind {kind!r} - use one of {sorted(KINDS)}")
            continue
        if kind == "copy" and not brief["lang"] and t["target"].strip() != t["source"].strip():
            errs.append(f"{name}: 1:1 mode (no --lang) keeps copy verbatim - target must equal "
                        f"source {t['source']!r}")
        if kind in ("copy", "brand") and OFFER_RE.search(t["source"]):
            errs.append(f"{name}: {t['source']!r} looks like a price/discount/bundle - set kind to "
                        "price, offer or guarantee")
        for field in NEEDS.get(kind, ()):
            if not brief.get(field):
                errs.append(f"{name}: a {kind} text needs our {field} in brief.json - ask the user, "
                            "never keep the competitor's")
        if kind in ("price", "offer", "guarantee"):
            stray = [n for n in nums(t["target"]) if n not in ours]
            if stray:
                errs.append(f"{name}: {t['target']!r} has numbers {stray} that are not in our "
                            "price/offer/guarantee")
        if kind == "price" and brief["currency"] and brief["currency"] not in t["target"]:
            errs.append(f"{name}: price {t['target']!r} lacks our currency {brief['currency']!r}")
        for comp in comps:
            if comp in t["target"].lower():
                errs.append(f"{name}: competitor name {comp!r} left in target text {t['target']!r}")
    for comp in comps:
        if comp in e["scene"].lower():
            errs.append(f"{name}: competitor name {comp!r} in scene - describe the product generically")
    for s in e.get("swaps", []):
        if not s.get("from") or not s.get("to"):
            errs.append(f"{name}: a swap needs from and to: {s}")
    if e["has_product"] and not brief["product_image"]:
        errs.append(f"{name}: product swap needs brief.product_image - ask the user, never generate one")
    return errs


def cmd_build(a):
    job = Path(a.job)
    brief, ads = load(job / "brief.json"), load(job / "ads.json")
    spell = {s.zfill(2) for s in a.spell}
    errs = [] if a.allow_short else set_problems(job, brief)
    for name, e in ads.items():
        if not e.get("skip"):
            errs += ad_problems(name, e, brief)
    if errs:
        sys.exit("build refused:\n  " + "\n  ".join(errs))
    refs = job / "Elements" / "_refs"
    prod_ref = refs / "product.png"
    if brief["product_image"]:
        Image.open(job / "01_originals" / brief["product_image"]).save(prod_ref)
    prompts = []
    for name, e in ads.items():
        if e.get("skip"):
            continue
        nn = name[:2]
        ref = refs / f"ref_{nn}.png"
        bands = pad_ref(job / "01_originals" / name, ref, e["aspect"]) if e["padded"] else None
        if not bands:
            Image.open(job / "01_originals" / name).convert("RGB").save(ref)
        r = [str(ref.resolve())] + ([str(prod_ref.resolve())] if e["has_product"] else [])
        prompts.append({"line": nn, "source": name, "aspect": e["aspect"], "refs": r,
                        "prompt": prompt_for(e, brief, bands, nn in spell)})
    save(job / "prompts.json", {"engine": brief.get("engine", "flow"), "slug": brief["code"].lower(),
                                "project_dir": str(job.resolve()),
                                "lines": prompts})
    print(f"{len(prompts)} prompts -> prompts.json (slug {brief['code'].lower()})")


# ---------------------------------------------------------------------------- finish
def fold(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if c.isalnum() or c == " ")


def text_check(path, e, comps):
    from rapidocr_onnxruntime import RapidOCR
    res, _ = RapidOCR()(str(path))
    raw = " ".join(r[1] for r in (res or []))
    seen = fold(raw)
    tokens = seen.split()
    miss = []
    for t in e["texts"]:
        for w in fold(t["target"]).split():
            if len(w) < 3 or w.isdigit():
                continue
            best = max((difflib.SequenceMatcher(None, w, k).ratio() for k in tokens), default=0)
            if best < 0.85:
                miss.append(w)
        have = nums(raw)
        miss += [f"number {n}" for n in nums(t["target"]) if n not in have]
    found_comp = [c for c in comps if fold(c) in seen]
    stray = [] if e["has_text"] else [k for k in tokens if len(k) > 2]
    return miss, found_comp, stray


def cmd_finish(a):
    job = Path(a.job)
    brief, ads = load(job / "brief.json"), load(job / "ads.json")
    picks = dict(p.split("=") for p in a.pick)
    stills = list((job / "Elements" / "Stills").glob("*.png"))
    bad, record = 0, {}
    for name, e in ads.items():
        if e.get("skip"):
            continue
        nn = name[:2]
        want = picks.get(nn) or picks.get(nn.lstrip("0"))
        pat = re.compile(rf"_line0*{int(nn)}" + (rf"_{want}" if want else "") + r"\.png$")
        hit = [s for s in stills if pat.search(s.name)]
        if len(hit) != 1:
            print(f"  {nn}: {len(hit)} still(s) match - expected 1" + (" (use --pick)" if hit else ""))
            bad += 1
            continue
        im = Image.open(hit[0]).convert("RGB")
        if e["padded"]:
            W, H = im.size
            r = e["size"][0] / e["size"][1]
            w, h = (W, round(W / r)) if W / H < r else (round(H * r), H)
            im = im.crop(((W - w) // 2, (H - h) // 2, (W - w) // 2 + w, (H - h) // 2 + h))
        dst = job / "02_localized" / f"{Path(name).stem}.png"
        if dst.exists():
            k = 2
            while (job / "02_localized" / f"{Path(name).stem}_v{k}.png").exists():
                k += 1
            dst = dst.with_name(f"{Path(name).stem}_v{k}.png")  # never overwrite a prior take
        im.save(dst)
        miss, comp, stray = text_check(dst, e, competitors(brief, e))
        flags = ([f"misspelt/missing: {', '.join(miss)}"] if miss else []) \
            + ([f"COMPETITOR NAME STILL VISIBLE: {', '.join(comp)}"] if comp else []) \
            + ([f"text on a no-text ad: {' '.join(stray[:8])}"] if stray else [])
        bad += bool(flags)
        record[dst.name] = flags
        print(f"  {nn}: {hit[0].name} -> {dst.name}  {im.size[0]}x{im.size[1]}  "
              + ("TEXT OK" if not flags else "CHECK: " + " | ".join(flags)))
    prev = load(job / "_finish.json") if (job / "_finish.json").exists() else {}
    save(job / "_finish.json", {**prev, **record})
    print("\nOCR folds accents (o = ö): confirm characters, prices and flags by eye on the "
          "side-by-side.")
    sys.exit(1 if bad else 0)


# ---------------------------------------------------------------------------- deliver
def rc(*args):
    r = subprocess.run(["rclone", *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"rclone {' '.join(args[:2])} failed: {r.stderr.strip()[-400:]}")
    return r.stdout


def cmd_deliver(a):
    job = Path(a.job)
    brief = load(job / "brief.json")
    prof = profile(job, brief)
    base = {p.stem: p for p in (job / "02_localized").iterdir()
            if p.suffix.lower() in IMG | VID and not re.search(r"_v\d+$", p.stem)}
    for name in a.use:  # a picked later take replaces its base, never ships beside it
        take = job / "02_localized" / name
        if not take.exists():
            sys.exit(f"--use: {name} not in 02_localized")
        base[re.sub(r"_v\d+$", "", take.stem)] = take
    src = sorted(base.values(), key=natural)
    numbered = [(a.start + i, s) for i, s in enumerate(src)]
    if a.only:  # feedback fixes: just these ads, original numbers, their NEWEST take
        numbered = [(n, s if s.name in a.use else newest(s)) for n, s in numbered
                    if s.name[:2] in {o.zfill(2) for o in a.only}]
    checks = load(job / "_finish.json") if (job / "_finish.json").exists() else {}
    held = [f"{s.name}: {checks[s.name] if s.name in checks else 'never checked - run finish'}"
            for _, s in numbered if s.suffix.lower() in IMG  # videos: checked by eye (recipe)
            and checks.get(s.name, True) and s.name[:2] not in a.accept]
    if held:
        sys.exit("deliver refused - text check not passed (fix, or the user accepts with --accept NN):\n  "
                 + "\n  ".join(held))
    stem = f"{brief['code']}-S{a.set}"
    out = job / "03_delivery"
    tail = f"-{a.suffix}" if a.suffix else ""
    plan = [(s, out / (prof["delivery_pattern"].format(code=brief["code"], set=a.set, n=n)
                       + tail + s.suffix.lower())) for n, s in numbered]
    clashes = [d.name for _, d in plan if d.exists()]
    if clashes and not (a.upload and len(clashes) == len(plan)):
        sys.exit(f"refusing to overwrite delivery files: {clashes} (use --start, --set or --suffix)")
    for s, d in plan:
        if not d.exists():
            clean(s, d)
        left = leftovers(d)
        if left:
            sys.exit(f"{d.name} still carries metadata: {left}")
        print(f"  {s.name:40} -> {d.name}  CLEAN")
    if a.upload:
        dest = f"{a.upload.rstrip('/')}/{stem}"
        have = set(rc("lsf", dest).split()) if subprocess.run(
            ["rclone", "lsf", dest], capture_output=True).returncode == 0 else set()
        taken = [d.name for _, d in plan if d.name in have]
        if taken:
            sys.exit(f"{dest} already has {taken} - use --start, --set or --suffix, never overwrite")
        for _, d in plan:
            rc("copyto", str(d), f"{dest}/{d.name}")
        landed = set(rc("lsf", dest).split())
        missing = [d.name for _, d in plan if d.name not in landed]
        if missing:
            sys.exit(f"upload incomplete, missing: {missing}")
        print(f"\nuploaded {len(plan)} files to {dest}, all present")
    else:
        print(f"\n{len(plan)} files ready in {out} (not uploaded)")
    if a.only:
        print("\nFeedback fixes: tell the reviewer which ads were corrected: "
              + ", ".join(d.name for _, d in plan))
        return
    if prof["status_value"]:
        print(f"\nStatus Sheet (the user does this): add the {len(plan)} ads for {brief['product']} "
              f"to the Ads table, set Ad Status to \"{prof['status_value']}\".")
    if prof["notify_template"]:
        print("Notify message (the user sends it):\n  "
              + prof["notify_template"].format(count=len(plan), product=brief["product"]))


# ---------------------------------------------------------------------------- review / doctor
def cmd_review(a):
    job = Path(a.job)
    ads = load(job / "ads.json")
    checks = load(job / "_finish.json") if (job / "_finish.json").exists() else {}
    H, font = 480, ImageFont.load_default(18)
    rows = []
    for name, e in ads.items():
        base = job / "02_localized" / f"{Path(name).stem}.png"
        if e.get("skip") or not base.exists():
            continue
        ours = newest(base)
        pair = [Image.open(p).convert("RGB") for p in (job / "01_originals" / name, ours)]
        pair = [im.resize((round(im.width * H / im.height), H), Image.LANCZOS) for im in pair]
        flags = checks.get(ours.name)
        rows.append((f"{name}  |  {ours.name}" + (f"   CHECK: {' | '.join(flags)}" if flags else ""), pair))
    if not rows:
        sys.exit("nothing to review - run finish first")
    sheet = Image.new("RGB", (max(p[0].width + p[1].width for _, p in rows) + 30,
                              len(rows) * (H + 44)), "white")
    d = ImageDraw.Draw(sheet)
    for i, (label, (orig, ours)) in enumerate(rows):
        y = i * (H + 44)
        d.text((10, y + 10), label, fill="red" if "CHECK" in label else "black", font=font)
        sheet.paste(orig, (10, y + 36))
        sheet.paste(ours, (20 + orig.width, y + 36))
    out = job / "review.png"
    sheet.save(out)
    print(f"{len(rows)} ads, original left, ours right -> {out}")


def cmd_doctor(a):
    bad = []

    def row(good, what, fix=""):
        print(f"  {'ok' if good else 'NO'}  {what}" + ("" if good else f"   -> {fix}"))
        if not good:
            bad.append(what)
    for mod in ("PIL", "rapidocr_onnxruntime"):
        try:
            __import__(mod)
            row(True, mod)
        except ImportError:
            row(False, mod, "pip install -r requirements.txt")
    for tool, why in (("rclone", "uploads"), ("ffmpeg", "video ads")):
        print(f"  {'ok' if shutil.which(tool) else '--'}  {tool} (optional, {why})")
    brief = load(Path(a.job) / "brief.json") if a.job else {}
    engines = [brief.get("engine", "flow")] if brief else ["flow", "higgsfield"]
    if "flow" in engines:
        print("flow:")
        src = Path(os.environ.get("FLOW_MCP_DIR", HERE / "flow-mcp")) / "src" / "flow_mcp"
        row(src.is_dir(), "flow-mcp bridge", "git submodule update --init (or set FLOW_MCP_DIR)")
        row(bool(shutil.which("uv")), "uv (runs the bridge)", "install uv: https://docs.astral.sh/uv/")
        root = os.environ.get("FLOW_WORK_ROOT")
        row(bool(root), "FLOW_WORK_ROOT", "set it to flow-mcp's work_root")
        if root and a.job:
            row(Path(a.job).resolve().is_relative_to(Path(root).resolve()), "job under FLOW_WORK_ROOT",
                "move the job folder inside it")
    if "higgsfield" in engines:
        print("higgsfield:")
        import hf
        row(bool(shutil.which(hf.HF)), "higgsfield CLI", "npm install -g @higgsfield/cli")
        if brief:
            problem = hf.check(brief["hf_login"], brief["hf_workspace"])
            row(not problem, f"login {brief['hf_login']} on workspace {brief['hf_workspace']}", problem)
        else:
            print("      logins: python hf.py status")
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("job")
    for f in ("--code", "--product"):
        p.add_argument(f, required=True)
    for f in ("--lang", "--market", "--product-image", "--competitor", "--currency", "--price",
              "--offer", "--guarantee", "--profile", "--hf-login", "--hf-workspace"):
        p.add_argument(f)
    p.add_argument("--engine", choices=sorted(ASPECTS), default="flow")
    p = sub.add_parser("fetch"); p.add_argument("job"); p.add_argument("urls")
    p = sub.add_parser("scan"); p.add_argument("job")
    p = sub.add_parser("build"); p.add_argument("job"); p.add_argument("--spell", nargs="*", default=[])
    p.add_argument("--allow-short", action="store_true", help="the user OK'd a set that breaks the profile")
    p = sub.add_parser("finish"); p.add_argument("job"); p.add_argument("--pick", nargs="*", default=[])
    p = sub.add_parser("deliver"); p.add_argument("job")
    p.add_argument("--set", type=int, default=1); p.add_argument("--start", type=int, default=1)
    p.add_argument("--only", nargs="*", default=[], help="NN of ads to (re)deliver, e.g. feedback fixes")
    p.add_argument("--suffix", default="", help="added to the name, e.g. v2 for a corrected ad")
    p.add_argument("--accept", nargs="*", default=[], help="NN of flagged ads the user accepted")
    p.add_argument("--upload"); p.add_argument("--use", nargs="*", default=[],
                                               help="deliver these _vN takes instead of the base")
    p = sub.add_parser("review"); p.add_argument("job")
    p = sub.add_parser("doctor"); p.add_argument("job", nargs="?")
    a = ap.parse_args()
    {"init": cmd_init, "fetch": cmd_fetch, "scan": cmd_scan, "build": cmd_build, "finish": cmd_finish,
     "review": cmd_review, "deliver": cmd_deliver, "doctor": cmd_doctor}[a.cmd](a)


if __name__ == "__main__":
    main()
