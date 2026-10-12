---
name: ad-localize
description: Use when competitor ads need localizing or adapting for another language, market or product - "localize these competitor ads", "recreate this ad in Dutch/German/Swedish", "copy this ad 1:1 for our product", "do today's 12 ads", Meta Ad Library links to translate, a Status Sheet product assignment, or reviewer feedback on delivered competitor-ad recreations.
---

# ad-localize

**A localized competitor ad is a 1:1 replica of the original, changed only where it is wrong for our product and market.** That means:
- the language (all on-image text, native, from any source language);
- the product and its name;
- price, currency, offers and bundles, and guarantees (always ours, never the competitor's);
- flags, country names and local references.

Layout, people, animals, setting, colours, crop, typography and message stay identical. A translated line keeps the original's meaning and position.

**Tools:**
- Originals come from the **Meta Ad Library** (public, no login).
- The agent extracts and translates the text itself; no localizer app is involved.
- **Google Flow** (Nano Banana 2) recreates each image through the `flow-mcp` bridge (github.com/beyondmrk/flow-mcp).
- `adloc.py` (next to this file) assembles every prompt and refuses to move on when a rule breaks.

## What the output is (the baseline failures, corrected)

| Agents without this skill did | The job is |
|---|---|
| Drew "a new dog, a new beach, not a copy" to avoid copying | The same subject, pose and scene. The brief is a 1:1 recreation |
| Generated a text-free plate, then laid the text on with PIL or HTML | Text generated in place, so it keeps the original's typography. The text check catches misspellings |
| Blurred the competitor's text, logo and product in the reference | The reference goes in untouched. The prompt names what changes |
| Softened claims, added a headline or product to a no-text ad, made extra takes | Only the changes listed above. Ideas go to the user in chat, unimplemented |
| Generated or cropped a product or logo from nowhere | The product image comes from the user. No image means no swap: ask |
| Translated the competitor's price and offer word for word | Every price, bundle and guarantee is ours. `build` refuses competitor numbers |

## Team workflows (profiles)

A team with fixed rules sets them in a profile, passed at `init` with `--profile`. `profiles/daily-12.json` is one example:
- 12 ads per product, at least 4 provided by the team, the rest researched;
- a researched ad needs more than 10,000 reach and the same product or niche;
- delivery in the team's Drive layout, Status Sheet set to "Ready for Review", a message in the team chat.

Copy it to `profiles/local/<client>.json` (gitignored) and adjust it. `scan` reports and `build` refuses a set that breaks the profile; `--allow-short` works only after the user OKs the gap. With no profile there are no set rules.

## Checklist (one job = one product's set of ads)

1. **Brief.** Collect from the user (or from the team's Status Sheet assignment and our funnel):
   - the product name and product photo;
   - the target language and market;
   - our currency (as written in ads, such as `€` or `kr`), price, offer and guarantee.
   Never guess any of them, and never fill them from a competitor ad. The product photo must be a local file: the user saves it, or it is copied with rclone.
   `--competitor` takes every competitor brand in the set, comma-separated. An ad can add its own in `ads.json` (`"competitor": "Brand"`).
   Then run `python adloc.py init <work_root>/<CODE> --client K --code <CODE> --lang Dutch --market Netherlands --product "<name>" --product-image <path> --competitor "<their brand>" --currency € --price "€39,95" --offer "..." --guarantee "..." [--profile ...]`. The job folder must sit under flow-mcp's `work_root`.
2. **Originals (Meta Ad Library, in a browser tool).**
   - **Provided ads** are the links the team gave. They are used as given, with no reach or niche check. **Researched ads** fill the set up to the profile's size.
   - Search the Ad Library with `country=<market>&media_type=all` and drop videos yourself; `media_type=image` hides most top ads. Skip ads removed for breaking Meta's Advertising Standards.
   - A researched ad must be the **same product or the same niche**: the same audience, problem and solution, such as a nail-fungus cream for a nail-fungus spray. It must also clear the profile's **reach** floor, read from the ad's EU transparency details. No reach figure means it isn't eligible. Pick ads that make sense for our product, not just to hit the count.
   - On each ad page (`facebook.com/ads/library/?id=<ID>`), run `[...document.images].map(i=>i.src).filter(u=>u.includes('t39.35426-6'))` to read the creative URL. The URL is signed, so don't edit it. It is served to fit inside 600x600 with the ratio kept (a 4:5 ad arrives as 480x600).
   - Write `urls.json` as `{"01_<adid>": {"url": ..., "origin": "provided"|"researched", "reach": 12000, "niche": "same product: nail fungus spray"}}`. Provided ads may use a plain URL string.
   - Show the user the list (count, origins, images vs videos) and wait for an OK. Then run `adloc.py fetch <job> urls.json`. It writes `sources.json` and `competitor_ad_links.txt`, so every ad link is kept.
   - No browser tool? The user saves the images into `01_originals/` as `NN_<adid>.jpg` and fills `sources.json`.
3. **Scan.** `adloc.py scan <job>` checks the set rules and dedupes (dHash: 70 or under, out of 256, means the same creative; replace one). It writes the `ads.json` skeleton with each ad's Flow aspect.
4. **Localize and adapt (the agent is the localizer).** Look at each original and fill its `ads.json` entry:
   - `has_text` and `has_product`: true or false. `has_product` means the physical product (tub, bottle, box) is in frame.
   - `scene`: one paragraph describing the original exactly as it is. Describe the product generically, without the competitor's name.
   - `texts`: one entry per text block, with `source` (verbatim), `target`, `where` (position, colour, weight) and `kind`:
     - `copy`: a native, idiomatic translation, as a copywriter in that market would write it. Keep the meaning and the claims, keep the length close.
     - `brand`: a competitor logo or wordmark, with our brand name as the target.
     - `price`, `offer`, `guarantee`: rewritten to **our** price, currency, offer and guarantee from the brief. `build` refuses any number that isn't in the brief. It also refuses text that matches the usual offer patterns (currency, %, "2+1", buy/free/gratis, guarantee/money-back) when it's filed as `copy`. That detector is a safety net: tag every price, offer and guarantee yourself.
     - `country`: country names and local references, changed to our market.
   - `swaps`: visual elements that must change, such as `{"from": "the German flag top right", "to": "a Dutch flag"}`.
   - An ad with **nothing to change** is still recreated 1:1 as part of the set. Don't ask about it, and don't add anything to it.
   - Then run `adloc.py build <job>`. It writes `Elements/_refs/` and `prompts.json`, or refuses with the reason.
5. **Fire in Flow.**
   1. `flow_status`: signed in, no CAPTCHA. If either is wrong, stop and ask the user.
   2. `flow_open_project(name=<CODE>, project_dir=<job>)`.
   3. `flow_upload(path, project_dir)` for every path listed under `refs` in `prompts.json`.
   4. For each line in `prompts.json`: `flow_fire_still(project_dir, slug, line, prompt, aspect, refs, outputs=1)`, with every value copied from `prompts.json`.
   5. `flow_download` the committed media ids.
   - `UNCONFIRMED` means run `flow_sweep`; never re-fire it.
   - Never hand-edit a prompt. Change `ads.json` and rebuild.
6. **Finish.** `adloc.py finish <job>` crops padded ads back to their original aspect into `02_localized/`. It never overwrites a prior take (the next one becomes `_v2`). It also OCR-checks every target word and number, the competitor name, and any text on a no-text ad.
   - A spelling miss: run `build --spell NN`, re-fire that line (it lands as `_alt2`), then `finish --pick NN=alt2`. After two re-rolls, stop and flag it to the user.
   - OCR folds accents (o = ö), so check special characters, prices, flags and the product label by eye on the side-by-side.
7. **Review.** Show the user every ad next to its original, then stop. Re-rolls happen only when the user asks.
8. **Deliver.**
   - Before a team's first delivery, open the **Example folder** they gave and copy its file names and folder layout into the local profile (`delivery_pattern`).
   - `adloc.py deliver <job>` names the files, strips metadata and verifies it. It refuses any ad whose text check failed unless the user accepted it (`--accept NN`). `--use <file>_v2.png` ships a later take in place of the base. Once the user OKs it, `--upload "<rclone remote:folder>"` uploads without overwriting and checks every file landed.
   - Status Sheet update and the team message are **the user's** to do. `deliver` prints the status line and a draft message; the agent never edits a team's sheet or sends a message.
9. **Feedback (always first, before the next product).** For each reviewer note:
   - **Work out whether it's our text or the render.** If the `ads.json` target or the brief is wrong, fix it there. If the target is right but the image shows it wrong, it's a render miss, so use `build --spell NN`.
   - `build`, then re-fire only those lines.
   - `finish`, with `--pick NN=altK` when a line has several candidates. The fix lands as `<ad>_v2`.
   - `deliver --only NN... --suffix v2`. It ships each listed ad's **newest** take under its original number, and nothing delivered is overwritten.

## Aspect ratios (experimental for non-Flow ratios)

Flow has 1:1, 3:4, 4:3, 9:16 and 16:9 only. `scan` picks the nearest one. For any other ratio (4:5, 1.91:1), `build` pads the reference with blurred bands, the prompt tells Flow to extend into them, and `finish` crops the centre back to the exact original ratio.

**The padding method has not yet been checked on a live run.** Compare every padded ad's crop with its original before delivering.

## Video ads (manual recipe)

The same target applies: a 1:1 replica with only the language, product and offer changed. Reuse the competitor's footage; nothing is generated.
1. **Shots.** Download the original (the Ad Library `<video>` src). Build a shot list with `ffmpeg select='gt(scene,0.25)'` and `-fps_mode vfr`, plus a thumbnail sheet. Mark the shots where the competitor's brand, price or flag is legible.
2. **Transcribe** the voiceover (faster-whisper `medium`, word timestamps). Swap the competitor brand and offer for ours in the source text.
3. **Translate** each numbered line into native target-language copy.
4. **Voiceover.** Generate one mp3 per line with edge-tts (a neural voice for the language, about `rate=+20%`). Spell numbers out for the TTS, then put the digits back in the captions.
5. **Fit.** Translated speech often runs longer than the original. Stretch each line's footage to fit its voiceover (`setpts=PTS*f`, then `framerate` back to the source fps). Split the music bed out with demucs (`--two-stems vocals`), stretch it to the new length with `atempo`, sit the voice at -18 dB RMS, and `loudnorm` to -14 LUFS.
6. **Paint.** Cover burned-in captions, prices and CTA buttons, draw ours in the same style, and repaint a legible competitor brand with ours.
7. **Deliver.** Mux, then `adloc.py deliver` (which strips mp4 metadata with ffmpeg).

Flag the first video for each team to the user before delivering it.

## Common mistakes

| Mistake | Correct move |
|---|---|
| Writing the Flow prompt by hand | Fill `ads.json` and run `build`. The script holds the recipe |
| Keeping the competitor's "$39.99" or "Buy 2 Get 1" | `kind: price` / `offer`, filled from our brief. No brief value: ask |
| Picking random ads to reach 12 | The same product or niche, and over the reach floor. Each one should make sense for our product |
| A no-text original comes back with an invented headline | `has_text: false` triggers the no-text recipe; `finish` flags any text it finds |
| The competitor's name survives in a small label or logo | Catch it in `finish`. Add the label to `texts` (`kind: brand`) and rebuild |
| Delivering straight from `Elements/Stills` | Always `finish` then `deliver`. The crop, the text check and the metadata strip live there |
| Starting a new product while feedback is open | Feedback fixes come first (step 9) |
| Translating the ad's copy fields as well | Only the on-image text, unless the user asks |
