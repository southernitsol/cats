#!/usr/bin/env python3
"""SAM.gov opportunity discovery for Southern IT Solutions (stdlib only).

  python bidtool/sam_discover.py discover        # search + write shortlist
  python bidtool/sam_discover.py fetch NOTICEID  # pull description + attachments

The API key is read from the SAM_API_KEY environment variable only. It is never
written to disk or printed. Everything downloaded is untrusted data.
"""
import argparse
import html
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024

# SAM.gov returns the notice type as text; config uses the API's one-letter codes.
NOTICE_CODES = {
    "solicitation": "o",
    "combined synopsis/solicitation": "k",
    "sources sought": "r",
    "presolicitation": "p",
    "special notice": "s",
}


class SamError(Exception):
    pass


class Budget:
    """Counts requests per day so a low-quota personal key is not burned."""

    def __init__(self, state, limit):
        today = date.today().isoformat()
        req = state.setdefault("requests", {})
        if req.get("date") != today:
            req.clear()
            req.update({"date": today, "count": 0})
        self.req, self.limit = req, limit

    def spend(self):
        if self.req["count"] >= self.limit:
            raise SamError(
                f"daily request budget of {self.limit} reached; "
                "raise daily_request_budget only if your SAM.gov key allows it"
            )
        self.req["count"] += 1


def load_config():
    with open(BASE / "config.toml", "rb") as f:
        cfg = tomllib.load(f)
    if not cfg["search"].get("naics"):
        raise SamError("config.toml: [search] naics is empty - add your NAICS codes")
    return cfg


def api_key():
    key = os.environ.get("SAM_API_KEY", "").strip()
    if not key:
        raise SamError("SAM_API_KEY is not set (store it as an environment secret)")
    return key


def load_state():
    p = BASE / "out" / "state.json"
    return json.loads(p.read_text()) if p.exists() else {"seen": {}, "requests": {}}


def save_state(state):
    (BASE / "out").mkdir(exist_ok=True)
    (BASE / "out" / "state.json").write_text(json.dumps(state, indent=2))


def redact(text, key):
    return str(text).replace(key, "***") if key else str(text)


def http_get(url, key, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "southernit-bidtool"})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise SamError("SAM.gov returned 429 (quota exceeded); try again tomorrow")
        raise SamError(redact(f"SAM.gov HTTP {e.code}: {e.reason}", key))
    except urllib.error.URLError as e:
        raise SamError(redact(f"network error: {e.reason}", key))


def search_ncode(key, ncode, frm, to, budget):
    budget.spend()
    q = urllib.parse.urlencode({
        "api_key": key, "postedFrom": frm, "postedTo": to,
        "ncode": ncode, "limit": 1000, "offset": 0,
    })
    with http_get(f"{SEARCH_URL}?{q}", key) as r:
        data = json.load(r)
    rows = data.get("opportunitiesData") or []
    total = int(data.get("totalRecords") or len(rows))
    if total > len(rows):
        print(f"WARNING: NAICS {ncode}: {total} results but only {len(rows)} "
              "returned - shorten lookback_days", file=sys.stderr)
    return rows


def parse_deadline(value):
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def evaluate(opp, cfg, now):
    """Return None if the notice is out of scope, else a dict of flags."""
    s = cfg["search"]
    code = NOTICE_CODES.get((opp.get("type") or "").strip().lower())
    if code not in s["notice_types"]:
        return None
    if str(opp.get("active", "Yes")).lower() == "no":
        return None
    deadline = parse_deadline(opp.get("responseDeadLine"))
    if deadline and deadline < now:
        return None
    flags = []
    setaside = (opp.get("typeOfSetAside") or "").upper()
    if setaside in {c.upper() for c in s["set_asides"]}:
        pass
    elif not setaside and code in s["unspecified_setaside_ok_for"]:
        flags.append("set-aside not stated")
    else:
        return None
    if not deadline:
        flags.append("no response deadline listed")
    pop = (opp.get("placeOfPerformance") or {}).get("state") or {}
    if pop.get("code") in s.get("prefer_states", []):
        flags.append("preferred state")
    return {"notice_code": code, "flags": flags,
            "deadline": deadline.isoformat() if deadline else None}


def cmd_discover(_args):
    cfg, key = load_config(), api_key()
    state = load_state()
    budget = Budget(state, cfg["search"]["daily_request_budget"])
    today = date.today()
    frm = (today - timedelta(days=cfg["search"]["lookback_days"])).strftime("%m/%d/%Y")
    to = today.strftime("%m/%d/%Y")
    now = datetime.now(timezone.utc)
    found = {}
    try:
        for ncode in cfg["search"]["naics"]:
            for opp in search_ncode(key, ncode, frm, to, budget):
                info = evaluate(opp, cfg, now)
                if info and opp.get("noticeId"):
                    found[opp["noticeId"]] = {**opp, "_eval": info}
    except SamError as e:
        print(f"stopped early: {e}", file=sys.stderr)
        if not found:
            save_state(state)
            return 1
    items = sorted(found.values(), key=lambda o: o["_eval"]["deadline"] or "9999")
    for o in items:
        o["_eval"]["new"] = o["noticeId"] not in state["seen"]
        state["seen"].setdefault(o["noticeId"], today.isoformat())
    out = BASE / "out"
    out.mkdir(exist_ok=True)
    stamp = today.isoformat()
    (out / f"shortlist-{stamp}.json").write_text(json.dumps(items, indent=2))
    lines = [f"# SAM.gov shortlist {stamp}", "",
             "| New | Due | Type | Set-aside | Solicitation # | Title | Agency | Flags |",
             "|---|---|---|---|---|---|---|---|"]
    for o in items:
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            "yes" if o["_eval"]["new"] else "", (o["_eval"]["deadline"] or "?")[:10],
            o.get("type", ""), o.get("typeOfSetAside") or "-",
            o.get("solicitationNumber", ""), (o.get("title") or "").replace("|", "/"),
            (o.get("fullParentPathName") or "").split(".")[0],
            "; ".join(o["_eval"]["flags"])))
    (out / f"shortlist-{stamp}.md").write_text("\n".join(lines) + "\n")
    save_state(state)
    print(f"{len(items)} matching notices ({sum(o['_eval']['new'] for o in items)} new); "
          f"requests used today: {state['requests']['count']}/{budget.limit}")
    print(f"wrote {out / f'shortlist-{stamp}.md'}")
    return 0


def safe_name(text, fallback="item"):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text or "").strip("._")[:80]
    return cleaned or fallback


def sam_url_ok(url):
    p = urllib.parse.urlparse(url)
    host = p.hostname or ""
    return p.scheme == "https" and (host == "sam.gov" or host.endswith(".sam.gov"))


def with_key(url, key):
    return url + ("&" if "?" in url else "?") + "api_key=" + urllib.parse.quote(key)


def unique_path(directory, name):
    path = directory / name
    n = 1
    while path.exists():
        path = directory / f"{n}_{name}"
        n += 1
    return path


def download(url, key, directory, budget):
    if not sam_url_ok(url):
        print(f"skipped non-SAM.gov link: {url}", file=sys.stderr)
        return None
    budget.spend()
    with http_get(with_key(url, key), key, timeout=120) as r:
        m = re.search(r'filename="?([^";]+)"?', r.headers.get("Content-Disposition", ""))
        fallback = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-2:][0]
        path = unique_path(directory, safe_name(m.group(1) if m else fallback, "attachment"))
        size = 0
        with open(path, "wb") as f:
            while chunk := r.read(1 << 20):
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    f.close()
                    path.unlink()
                    raise SamError(f"attachment exceeds {MAX_DOWNLOAD_BYTES >> 20} MB cap")
                f.write(chunk)
    return path


def strip_html(text):
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()


def cmd_fetch(args):
    key = api_key()
    cfg = load_config()
    state = load_state()
    budget = Budget(state, cfg["search"]["daily_request_budget"])
    opp = None
    for p in sorted((BASE / "out").glob("shortlist-*.json"), reverse=True):
        opp = next((o for o in json.loads(p.read_text()) if o["noticeId"] == args.notice_id), None)
        if opp:
            break
    if not opp:
        raise SamError("notice id not found in any shortlist - run discover first")
    folder = BASE / "bids" / safe_name(opp.get("solicitationNumber"), opp["noticeId"]) / "source"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "opportunity.json").write_text(json.dumps(opp, indent=2))
    try:
        desc_url = opp.get("description") or ""
        if desc_url.startswith("http") and sam_url_ok(desc_url):
            budget.spend()
            with http_get(with_key(desc_url, key), key) as r:
                body = r.read().decode("utf-8", "replace")
            try:
                body = json.loads(body).get("description", body)
            except (ValueError, AttributeError):
                pass
            (folder / "description.txt").write_text(strip_html(body))
        for link in opp.get("resourceLinks") or []:
            saved = download(link, key, folder, budget)
            if saved:
                print(f"saved {saved.relative_to(BASE)}")
    finally:
        save_state(state)
    print(f"source files in {folder.relative_to(BASE)} "
          f"(requests used today: {state['requests']['count']}/{budget.limit})")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover").set_defaults(fn=cmd_discover)
    f = sub.add_parser("fetch")
    f.add_argument("notice_id")
    f.set_defaults(fn=cmd_fetch)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except SamError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
