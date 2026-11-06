# bidtool - SAM.gov bid discovery and draft generation

Finds SDVOSB/VOSB set-asides, solicitations, and sources sought on SAM.gov and
has Claude draft the response package. **It never submits or sends anything.**

## One-time setup

1. Edit `config.toml`: add your NAICS codes, company details, rates, margin, and
   list only the statuses you are currently verified for in `certifications`.
2. Store your SAM.gov key as an **environment secret named `SAM_API_KEY`**
   (Claude Code on the web: environment settings -> secrets). Do not paste it in chat
   or commit it.
3. Check the key's daily quota on your SAM.gov account page. Personal keys can be
   as low as 10 requests/day; set `daily_request_budget` to match. Discovery costs
   one request per NAICS code per run, and each attachment/description fetch costs more.

## Daily use

```bash
python3 bidtool/sam_discover.py discover        # writes out/shortlist-<date>.md
python3 bidtool/sam_discover.py fetch <noticeId> # description + attachments
```

Then ask Claude: "Run the gov-bid-generator skill on today's shortlist." Drafts land
in `bids/<solicitation>/`. Review `review-notes.md` first, fix every `PRICE NEEDED`
and `TODO-OWNER`, then submit through the channel in `submission-checklist.md`.

To automate the morning run, schedule a task that runs the skill and posts the
ranked summary to you; it stops at drafts.

## Tests

```bash
python3 -I -m unittest discover -s bidtool/tests
```

The SAM.gov calls are unit-tested against mocked responses only; the first live
run is the real check of field names and quota behavior.
