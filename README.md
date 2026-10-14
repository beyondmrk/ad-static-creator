# ad-static-creator

A Claude Code skill that recreates competitor static ads **1:1** for your product (the same
layout, people, colours and typography), changed only where it is wrong for you:
- the competitor's product and name, replaced with yours;
- prices, currency, offers and guarantees, replaced with yours;
- in **localize mode** also: the on-image text, made native in the target language, and the
  flags and country references, changed to your market.

In **1:1 mode** (no target language) the copy stays word for word, and the script refuses any
changed line.

Images are recreated on Nano Banana by one of two engines, chosen per job:
- **Google Flow** through the bundled [flow-mcp](https://github.com/beyondmrk/flow-mcp) bridge
  (stills cost 0 credits on Google AI Ultra);
- **Higgsfield** through its CLI, with several logins side by side. Each job names its login
  and workspace, and the fire refuses anything else.

The agent reads and translates the text itself. `adloc.py` assembles every generation prompt
from a structured file and refuses to move on when something is missing or wrong. Team rules
such as "12 ads a day, 4 provided, the rest researched at 10,000+ reach" live in a **profile**
(`profiles/daily-12.json` is an example), and the script enforces them.

## How a job runs

1. **init**: create the job folder with the brief: product, our price, currency, offer and
   guarantee, the engine, and (for localize mode) the language and market.
2. **fetch**: download the competitor creatives from their Meta Ad Library links, and record
   each one's link, origin (provided or researched), reach and niche note.
3. **scan**: check the profile's set rules, drop duplicates (perceptual hash), and pick each
   ad's aspect ratio for the engine.
4. **fill `ads.json`**: the agent writes a scene description, every text block with its
   original, its target and its kind (copy, brand, price, offer, guarantee or country), and
   any visual swaps, such as flags.
5. **build**: validates everything and assembles the prompts. It refuses:
   - unfilled fields;
   - a competitor name left in;
   - a price or offer containing numbers that aren't in our brief;
   - offer-looking text filed as plain copy;
   - changed copy in 1:1 mode;
   - a product swap with no product image;
   - a set that breaks the profile.
6. **fire**: `flow_run.py` (Flow) or `hf.py fire` (Higgsfield: quotes the credits first, and
   spends only with `--yes`).
7. **finish**: crop back to the original aspect, then OCR-check the text. It flags misspelt
   or missing words, a leftover competitor name, and text on an ad that had none.
8. **review**: one sheet with every original next to its recreation.
9. **deliver**: name the files with the profile's pattern, strip all metadata, verify it, and
   optionally upload with rclone (never overwriting). An ad that failed the text check is
   refused unless the user accepts it. It also prints the status-sheet line and a draft team
   message for the user to send.
10. **feedback**: the reviewer's fixes are re-delivered with `--only NN --suffix v2`.

The agent stops for the user's OK before downloading, before any paid fire, and after the
results, and never re-rolls without being asked. `SKILL.md` has the full checklist.

## Install (one line, Windows)

```powershell
irm https://raw.githubusercontent.com/beyondmrk/ad-static-creator/main/bootstrap.ps1 | iex
```

It does the whole setup and ends with a check that prints `READY` or exactly what is missing:
- installs Git, Python, Node, uv and the Higgsfield CLI when they are missing;
- clones the skill, with the Flow bridge, into `~/.claude/skills/ad-static-creator`;
- configures the bridge (jobs go in `~/ad-static-jobs`) and registers its MCP server with
  Claude Code;
- opens the Flow window and walks you through your first Higgsfield login.

Run the same line again to update. The only steps it can't do for you are the sign-ins: Google
in the Flow window, and Higgsfield in the browser. To add another Higgsfield account:
`python hf.py add <name>`.

`init` refuses to start a job until this machine passes the same check, so a half-finished
install can't produce a half-finished job.

macOS / Linux (Higgsfield engine only, because the Flow bridge needs Windows and Edge):
```bash
git clone --recurse-submodules https://github.com/beyondmrk/ad-static-creator ~/.claude/skills/ad-static-creator
python3 ~/.claude/skills/ad-static-creator/install.py --engine higgsfield
```

You need your own accounts: Google Flow (stills are free on Google AI Ultra), Higgsfield, or
both. A browser tool for the agent lets it read Meta Ad Library pages; without one, save the
images into `01_originals/` by hand. The manual video recipe also needs ffmpeg,
faster-whisper, edge-tts and demucs.

Then ask Claude Code something like *"recreate these 5 competitor ads 1:1 for our product on
Higgsfield, login team"* or *"localize these ads into German"* and paste the Ad Library links.

## Known limits

- **Aspect ratios.** Flow offers 1:1, 3:4, 4:3, 9:16 and 16:9; Higgsfield adds 4:5, 5:4, 3:2,
  2:3 and 21:9. A ratio the engine lacks is padded and cropped back. That method is
  **experimental**, so compare every padded ad's crop with its original.
- **Special characters.** The OCR check ignores accents (ö reads as o), so check special
  characters by eye.
- **Ad Library images** come at no more than 600 px on the long side, so that is the
  reference resolution.
- **Text in the image is generated by the model.** Re-roll misspellings: `build --spell NN`
  spells the words out letter by letter in the prompt.
- **Numbers with a space as thousands separator** ("1 299 kr") are read as one number; two
  numbers separated only by a space in one text block are merged the same way.

## Tests

`python -m unittest test_adloc`

## License

MIT, see `LICENSE`. The `flow-mcp` submodule carries its own license.
