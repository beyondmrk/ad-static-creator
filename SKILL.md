---
name: ad-static-creator
description: Use when competitor static ads need recreating 1:1 for our product, with or without localizing to another language or market - "copy this ad 1:1 for our product", "recreate these competitor ads", "localize these competitor ads", "recreate this ad in Dutch/German/Swedish", "do today's 12 ads", Meta Ad Library links to recreate or translate, a Status Sheet product assignment, or reviewer feedback on delivered competitor-ad recreations. Generates on Google Flow or Higgsfield.
---

# ad-static-creator

**A recreated competitor ad is a 1:1 replica of the original, changed only where it is wrong for our product.** Always:
- the product and its name;
- price, currency, offers and bundles, and guarantees (always ours, never the competitor's).

Two modes, set at `init`:
- **1:1 mode** (no `--lang`): the text stays word for word in the original language. `build` refuses a `copy` text whose target differs from its source.
- **Localize mode** (`--lang`, `--market`): all on-image text becomes native in the target language, and flags, country names and local references move to our market.

Layout, people, animals, setting, colours, crop, typography and message stay identical. A translated line keeps the original's meaning and position.

**Tools:**
- Originals come from the **Meta Ad Library** (public, no login).
- The agent extracts and translates the text itself; no localizer app is involved.
- One engine per job (`--engine`), both on Nano Banana:
  - **flow** (default): Google Flow through the bundled `flow-mcp` bridge, fired by `flow_run.py`. Stills cost 0 credits on Google AI Ultra.
  - **higgsfield**: the Higgsfield CLI on a named login and workspace, fired by `hf.py fire`. Costs credits, and supports 4:5, 5:4, 3:2, 2:3 and 21:9 natively.
- `adloc.py` (next to this file) assembles every prompt and refuses to move on when a rule breaks. `python adloc.py doctor [<job>]` checks the setup.

## What the output is (the baseline failures, corrected)

| Agents without this skill did | The job is |
|---|---|
| Drew "a new dog, a new beach, not a copy" to avoid copying | The same subject, pose and scene. The brief is a 1:1 recreation |
| Generated a text-free plate, then laid the text on with PIL or HTML | Text generated in place, so it keeps the original's typography. The text check catches misspellings |
| Blurred the competitor's text, logo and product in the reference | The reference goes in untouched. The prompt names what changes |
| Softened claims, added a headline or product to a no-text ad, made extra takes | Only the changes listed above. Ideas go to the user in chat, unimplemented |
| Generated or cropped a product or logo from nowhere | The product image comes from the user. No image means no swap: ask |
| Translated the competitor's price and offer word for word | Every price, bundle and guarantee is ours. `build` refuses competitor numbers |
| "Improved" the copy in a 1:1 job | 1:1 mode keeps copy verbatim. `build` refuses a changed line |

## Team workflows (profiles)

A team with fixed rules sets them in a profile, passed at `init` with `--profile`. `profiles/daily-12.json` is one example:
- 12 ads per product, at least 4 provided by the team, the rest researched;
- a researched ad needs more than 10,000 reach and the same product or niche;
- delivery in the team's Drive layout, Status Sheet set to "Ready for Review", a message in the team chat.

Copy it to `profiles/local/<team>.json` (gitignored) and adjust it. `scan` reports and `build` refuses a set that breaks the profile; `--allow-short` works only after the user OKs the gap. With no profile there are no set rules.

## Higgsfield logins (several accounts side by side)

Each login is a folder under `~/.hf-logins/<name>`; the CLI runs with that folder as its home, so logins never sign each other out.
- `python hf.py add <name>` makes the folder and prints the sign-in steps. **The user signs in and selects the workspace**, never the agent.
- `python hf.py status` lists every login: email, workspace, credits.
- A Higgsfield job names its login and workspace at `init` (`--hf-login`, `--hf-workspace` = the workspace id or name). `hf.py fire` refuses when that login is on another workspace. A mismatch goes to the user: never switch it yourself.

## Checklist (one job = one product's set of ads)

1. **Brief.** Collect from the user (or from the team's Status Sheet assignment and our funnel):
   - the product name and product photo;
   - 1:1 or localized, and for localized, the target language and market;
   - our currency (as written in ads, such as `€` or `kr`), price, offer and guarantee;
   - the engine, and for Higgsfield, which login and workspace.
   Never guess any of them, and never fill them from a competitor ad. The product photo must be a local file: the user saves it, or it is copied with rclone.
   `--competitor` takes every competitor brand in the set, comma-separated. An ad can add its own in `ads.json` (`"competitor": "Brand"`).
   Then run `python adloc.py init <job> --code <CODE> --product "<name>" --product-image <path> --competitor "<their brand>" --currency € --price "€39,95" --offer "..." --guarantee "..." [--lang Dutch --market Netherlands] [--engine higgsfield --hf-login <name> --hf-workspace <id>] [--profile ...]`. A Flow job folder must sit under flow-mcp's `work_root`.
2. **Originals (Meta Ad Library, in a browser tool).**
   - **Provided ads** are the links the team gave. They are used as given, with no reach or niche check. **Researched ads** fill the set up to the profile's size.
   - Search the Ad Library with `country=<market>&media_type=all` and drop videos yourself; `media_type=image` hides most top ads. Skip ads removed for breaking Meta's Advertising Standards.
   - A researched ad must be the **same product or the same niche**: the same audience, problem and solution, such as a nail-fungus cream for a nail-fungus spray. It must also clear the profile's **reach** floor, read from the ad's EU transparency details. No reach figure means it isn't eligible. Pick ads that make sense for our product, not just to hit the count.
   - On each ad page (`facebook.com/ads/library/?id=<ID>`), run `[...document.images].map(i=>i.src).filter(u=>u.includes('t39.35426-6'))` to read the creative URL. The URL is signed, so don't edit it. It is served to fit inside 600x600 with the ratio kept (a 4:5 ad arrives as 480x600).
   - Write `urls.json` as `{"01_<adid>": {"url": ..., "origin": "provided"|"researched", "reach": 12000, "niche": "same product: nail fungus spray"}}`. Provided ads may use a plain URL string.
   - Show the user the list (count, origins, images vs videos) and wait for an OK. Then run `adloc.py fetch <job> urls.json`. It writes `sources.json` and `competitor_ad_links.txt`, so every ad link is kept.
   - No browser tool? The user saves the images into `01_originals/` as `NN_<adid>.jpg` and fills `sources.json`.
3. **Scan.** `adloc.py scan <job>` checks the set rules and dedupes (dHash: 70 or under, out of 256, means the same creative; replace one). It writes the `ads.json` skeleton with each ad's aspect for the job's engine.
4. **Fill `ads.json` (the agent is the localizer).** Look at each original and fill its entry:
   - `has_text` and `has_product`: true or false. `has_product` means the physical product (tub, bottle, box) is in frame.
   - `scene`: one paragraph describing the original exactly as it is. Describe the product generically, without the competitor's name.
   - `texts`: one entry per text block, with `source` (verbatim), `target`, `where` (position, colour, weight) and `kind`:
     - `copy`: 1:1 mode: the target is the source, unchanged. Localize mode: a native, idiomatic translation, as a copywriter in that market would write it. Keep the meaning and the claims, keep the length close.
     - `brand`: a competitor logo or wordmark, with our brand name as the target.
     - `price`, `offer`, `guarantee`: rewritten to **our** price, currency, offer and guarantee from the brief. `build` refuses any number that isn't in the brief. It also refuses text that matches the usual offer patterns (currency, %, "2+1", buy/free/gratis, guarantee/money-back) when it's filed as `copy`. That detector is a safety net: tag every price, offer and guarantee yourself.
     - `country`: country names and local references, changed to our market (needs `--market`).
   - `swaps`: visual elements that must change, such as `{"from": "the German flag top right", "to": "a Dutch flag"}`.
   - An ad with **nothing to change** is still recreated 1:1 as part of the set. Don't ask about it, and don't add anything to it.
   - Then run `adloc.py build <job>`. It writes `Elements/_refs/` and `prompts.json`, or refuses with the reason.
5. **Fire.** Never hand-edit a prompt: change `ads.json` and rebuild. Each still lands in `Elements/Stills` as `claude_<code>_lineNN.png`; a re-roll adds `_altN` and never replaces a take.
   - **Flow:** `uv run --directory flow-mcp python ../flow_run.py <absolute job path> [--only 03]` (uv runs inside flow-mcp, so a relative path breaks). It checks the bridge is signed in with no CAPTCHA, opens the project, uploads the refs and fires one still per line. A Flow problem stops the run: tell the user. `UNCONFIRMED` means run `flow_sweep`; never re-fire it.
   - **Higgsfield:** `python hf.py fire <job> [--only 03]` checks the login and workspace and prints the credit quote, then stops. Show the quote and wait for the user to say fire, then re-run with `--yes`. A line with no result stops the run: the job may still be running or already paid, so check `higgsfield generate list` before firing it again.
6. **Finish.** `adloc.py finish <job>` crops padded ads back to their original aspect into `02_localized/`. It never overwrites a prior take (the next one becomes `_v2`). It also OCR-checks every target word and number, the competitor name, and any text on a no-text ad.
   - A spelling miss: run `build --spell NN`, re-fire that line with `--reroll` (it lands as `_alt2`), then `finish --pick NN=alt2`. After two re-rolls, stop and flag it to the user.
   - OCR folds accents (o = ö), so check special characters, prices, flags and the product label by eye on the side-by-side.
7. **Review.** `adloc.py review <job>` writes `review.png`: every original next to our newest take, with flagged ads labelled in red. Show it to the user, then stop. Re-rolls happen only when the user asks.
8. **Deliver.**
   - Before a team's first delivery, open the **Example folder** they gave and copy its file names and folder layout into the local profile (`delivery_pattern`).
   - `adloc.py deliver <job>` names the files, strips metadata and verifies it. It refuses any ad whose text check failed unless the user accepted it (`--accept NN`). `--use <file>_v2.png` ships a later take in place of the base. Once the user OKs it, `--upload "<rclone remote:folder>"` uploads without overwriting and checks every file landed.
   - Status Sheet update and the team message are **the user's** to do. `deliver` prints the status line and a draft message; the agent never edits a team's sheet or sends a message.
9. **Feedback (always first, before the next product).** For each reviewer note:
   - **Work out whether it's our text or the render.** If the `ads.json` target or the brief is wrong, fix it there. If the target is right but the image shows it wrong, it's a render miss, so use `build --spell NN`.
   - `build`, then re-fire only those lines with `--reroll`.
   - `finish`, with `--pick NN=altK` when a line has several candidates. The fix lands as `<ad>_v2`.
   - `deliver --only NN... --suffix v2`. It ships each listed ad's **newest** take under its original number, and nothing delivered is overwritten.

## Aspect ratios

`scan` picks the engine's nearest ratio. Flow has 1:1, 3:4, 4:3, 9:16 and 16:9 only; Higgsfield adds 4:5, 5:4, 3:2, 2:3 and 21:9. For a ratio the engine lacks (4:5 on Flow, 1.91:1 on either), `build` pads the reference with blurred bands, the prompt tells the model to extend into them, and `finish` crops the centre back to the exact original ratio.

**The padding method has not yet been checked on a live run.** Compare every padded ad's crop with its original before delivering. On Higgsfield, most Meta ratios need no padding.

## Video ads (manual recipe)

The same target applies: a 1:1 replica with only the product and offer changed (and, in localize mode, the language). Reuse the competitor's footage; nothing is generated.
1. **Shots.** Download the original (the Ad Library `<video>` src). Build a shot list with `ffmpeg select='gt(scene,0.25)'` and `-fps_mode vfr`, plus a thumbnail sheet. Mark the shots where the competitor's brand, price or flag is legible.
2. **Transcribe** the voiceover (faster-whisper `medium`, word timestamps). Swap the competitor brand and offer for ours in the source text.
3. **Translate** (localize mode only) each numbered line into native target-language copy.
4. **Voiceover.** Generate one mp3 per line with edge-tts (a neural voice for the language, about `rate=+20%`). Spell numbers out for the TTS, then put the digits back in the captions.
5. **Fit.** Translated speech often runs longer than the original. Stretch each line's footage to fit its voiceover (`setpts=PTS*f`, then `framerate` back to the source fps). Split the music bed out with demucs (`--two-stems vocals`), stretch it to the new length with `atempo`, sit the voice at -18 dB RMS, and `loudnorm` to -14 LUFS.
6. **Paint.** Cover burned-in captions, prices and CTA buttons, draw ours in the same style, and repaint a legible competitor brand with ours.
7. **Deliver.** Mux, then `adloc.py deliver` (which strips mp4 metadata with ffmpeg).

Flag the first video for each team to the user before delivering it.

## Common mistakes

| Mistake | Correct move |
|---|---|
| Writing the generation prompt by hand | Fill `ads.json` and run `build`. The script holds the recipe |
| Keeping the competitor's "$39.99" or "Buy 2 Get 1" | `kind: price` / `offer`, filled from our brief. No brief value: ask |
| Picking random ads to reach 12 | The same product or niche, and over the reach floor. Each one should make sense for our product |
| A no-text original comes back with an invented headline | `has_text: false` triggers the no-text recipe; `finish` flags any text it finds |
| The competitor's name survives in a small label or logo | Catch it in `finish`. Add the label to `texts` (`kind: brand`) and rebuild |
| Firing Higgsfield straight away | `hf.py fire` without `--yes` quotes first; the user says fire |
| Fixing a wrong Higgsfield workspace yourself | Tell the user; they select it in the login's terminal |
| Delivering straight from `Elements/Stills` | Always `finish` then `deliver`. The crop, the text check and the metadata strip live there |
| Starting a new product while feedback is open | Feedback fixes come first (step 9) |
| Translating the ad's copy fields as well | Only the on-image text, unless the user asks |
