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

## Requirements

| Requirement | What it's for | Required? |
|---|---|---|
| [Claude Code](https://claude.com/claude-code) | Runs the skill | yes |
| Python 3.9+ with `pip install -r requirements.txt` | Pillow and RapidOCR: building, cropping, the text check, the review sheet | yes |
| **Flow engine:** a Google Flow account, [uv](https://docs.astral.sh/uv/), the `flow-mcp` submodule | Recreating on Flow | one engine |
| **Higgsfield engine:** `npm install -g @higgsfield/cli` and a Higgsfield account | Recreating on Higgsfield | one engine |
| A browser tool for the agent | Reading Meta Ad Library pages. Without one, save the images into `01_originals/` by hand | no |
| rclone | Uploading the delivery | no |
| ffmpeg, faster-whisper, edge-tts, demucs | The manual video recipe | video only |

## Install

```bash
git clone --recurse-submodules https://github.com/beyondmrk/ad-static-creator ~/.claude/skills/ad-static-creator
cd ~/.claude/skills/ad-static-creator
pip install -r requirements.txt
python adloc.py doctor
```

`doctor` lists what is missing for each engine. Then set up the engine(s) you use:

- **Flow:** follow `flow-mcp/README.md` (Edge profile, `config.toml` with `work_root`). Set
  `FLOW_WORK_ROOT` to the same folder: every Flow job lives inside it, and `init` refuses one
  that doesn't. Already have flow-mcp somewhere else? Set `FLOW_MCP_DIR` to it.
- **Higgsfield:** for each account, `python hf.py add <name>`, then sign in and select the
  workspace in a new terminal as it prints. `python hf.py status` shows every login, its
  workspace and credits. Logins live in `~/.hf-logins` (`HF_LOGINS` moves them).

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
