import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sam_discover as sd  # noqa: E402

NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)
FUTURE = (NOW + timedelta(days=10)).isoformat()
PAST = (NOW - timedelta(days=1)).isoformat()
CFG = {"search": {
    "naics": ["541512"], "notice_types": ["o", "k", "r", "p"],
    "set_asides": ["SDVOSBC", "SDVOSBS", "VSA", "VSS"],
    "unspecified_setaside_ok_for": ["r", "p"],
    "prefer_states": ["MS"], "daily_request_budget": 3, "lookback_days": 7}}


def opp(**kw):
    base = {"noticeId": "n1", "type": "Solicitation", "typeOfSetAside": "SDVOSBC",
            "responseDeadLine": FUTURE, "active": "Yes"}
    base.update(kw)
    return base


class EvaluateTests(unittest.TestCase):
    def test_sdvosb_solicitation_kept(self):
        self.assertIsNotNone(sd.evaluate(opp(), CFG, NOW))

    def test_vosb_codes_kept(self):
        for code in ("VSA", "VSS", "SDVOSBS"):
            self.assertIsNotNone(sd.evaluate(opp(typeOfSetAside=code), CFG, NOW), code)

    def test_other_setaside_dropped(self):
        for code in ("8A", "SBA", "WOSB", "HZC"):
            self.assertIsNone(sd.evaluate(opp(typeOfSetAside=code), CFG, NOW), code)

    def test_blank_setaside_dropped_for_solicitation_kept_for_sources_sought(self):
        self.assertIsNone(sd.evaluate(opp(typeOfSetAside=None), CFG, NOW))
        r = sd.evaluate(opp(type="Sources Sought", typeOfSetAside=None), CFG, NOW)
        self.assertIn("set-aside not stated", r["flags"])

    def test_expired_and_inactive_dropped(self):
        self.assertIsNone(sd.evaluate(opp(responseDeadLine=PAST), CFG, NOW))
        self.assertIsNone(sd.evaluate(opp(active="No"), CFG, NOW))

    def test_unwanted_notice_types_dropped(self):
        for t in ("Award Notice", "Special Notice", "Justification"):
            self.assertIsNone(sd.evaluate(opp(type=t), CFG, NOW), t)

    def test_missing_deadline_flagged(self):
        r = sd.evaluate(opp(responseDeadLine=None), CFG, NOW)
        self.assertIn("no response deadline listed", r["flags"])

    def test_preferred_state_flag(self):
        r = sd.evaluate(opp(placeOfPerformance={"state": {"code": "MS"}}), CFG, NOW)
        self.assertIn("preferred state", r["flags"])


class SafetyTests(unittest.TestCase):
    def test_budget_stops(self):
        b = sd.Budget({}, 2)
        b.spend(); b.spend()
        with self.assertRaises(sd.SamError):
            b.spend()

    def test_redact(self):
        self.assertEqual(sd.redact("bad key SECRET here", "SECRET"), "bad key *** here")

    def test_safe_name_blocks_traversal(self):
        self.assertNotIn("/", sd.safe_name("../../etc/passwd"))
        self.assertNotIn("..", sd.safe_name("../../etc/passwd"))
        self.assertEqual(sd.safe_name("", "fallback"), "fallback")

    def test_only_sam_hosts_receive_key(self):
        self.assertTrue(sd.sam_url_ok("https://sam.gov/api/prod/opps/v3/x/download"))
        self.assertTrue(sd.sam_url_ok("https://api.sam.gov/prod/x"))
        for bad in ("http://sam.gov/x", "https://evilsam.gov/x",
                    "https://sam.gov.evil.com/x", "https://example.com/x"):
            self.assertFalse(sd.sam_url_ok(bad), bad)

    def test_empty_naics_refused(self):
        with mock.patch.object(sd, "BASE", Path(tempfile.mkdtemp())):
            (sd.BASE / "config.toml").write_text('[search]\nnaics = []\n')
            with self.assertRaises(sd.SamError):
                sd.load_config()


class DiscoverEndToEnd(unittest.TestCase):
    def test_discover_writes_shortlist_and_dedupes(self):
        payload = {"totalRecords": 3, "opportunitiesData": [
            opp(noticeId="a", title="Keep", solicitationNumber="W1"),
            opp(noticeId="b", typeOfSetAside="8A"),
            opp(noticeId="c", responseDeadLine=PAST)]}
        tmp = Path(tempfile.mkdtemp())
        cfg_text = ('[search]\nnaics=["541512"]\nnotice_types=["o","k","r","p"]\n'
                    'set_asides=["SDVOSBC"]\nunspecified_setaside_ok_for=["r","p"]\n'
                    'lookback_days=7\ndaily_request_budget=5\nprefer_states=[]\n')
        (tmp / "config.toml").write_text(cfg_text)
        def fresh_response(*_a, **_kw):
            fake = mock.MagicMock()
            fake.__enter__.return_value = io.BytesIO(json.dumps(payload).encode())
            return fake

        with mock.patch.object(sd, "BASE", tmp), \
             mock.patch.dict("os.environ", {"SAM_API_KEY": "k"}), \
             mock.patch.object(sd, "http_get", side_effect=fresh_response), \
             mock.patch.object(sd, "datetime") as dt:
            dt.now.return_value = NOW
            dt.fromisoformat = datetime.fromisoformat
            self.assertEqual(sd.main(["discover"]), 0)
            files = list((tmp / "out").glob("shortlist-*.json"))
            items = json.loads(files[0].read_text())
            self.assertEqual([i["noticeId"] for i in items], ["a"])
            self.assertTrue(items[0]["_eval"]["new"])
            self.assertNotIn("api_key", (tmp / "out" / "state.json").read_text())
            self.assertEqual(sd.main(["discover"]), 1)  # same-day guard
            sd.main(["discover", "--force"])
            items2 = json.loads(sorted((tmp / "out").glob("shortlist-*.json"))[0].read_text())
            self.assertFalse(items2[0]["_eval"]["new"])


class RotationTests(unittest.TestCase):
    CODES = ["a", "b", "c", "d", "e"]

    def test_pick_codes_wraps(self):
        self.assertEqual(sd.pick_codes(self.CODES, 0, 2), (["a", "b"], 0))
        self.assertEqual(sd.pick_codes(self.CODES, 4, 2), (["e", "a"], 4))
        self.assertEqual(sd.pick_codes(self.CODES, 7, 2), (["c", "d"], 2))

    def test_codes_per_run_reserves_fetch_requests(self):
        s = {"naics": self.CODES * 2, "daily_request_budget": 10, "fetch_reserve": 5}
        self.assertEqual(sd.codes_per_run(s), 5)
        s["fetch_reserve"] = 0
        self.assertEqual(sd.codes_per_run(s), 10)
        s["naics"] = ["a"]
        self.assertEqual(sd.codes_per_run(s), 1)  # never more than the code list
        s.update(naics=self.CODES, fetch_reserve=10)
        with self.assertRaises(sd.SamError):
            sd.codes_per_run(s)

    def _run(self, tmp, args, fail_on=None):
        urls = []
        sp = tmp / "out" / "state.json"
        if sp.exists():  # simulate a new day: the request budget resets
            st = json.loads(sp.read_text())
            st.pop("requests", None)
            sp.write_text(json.dumps(st))

        def fake(url, key, timeout=60):
            code = url.split("ncode=")[1].split("&")[0]
            urls.append(code)
            if code == fail_on:
                raise sd.SamError("boom")
            r = mock.MagicMock()
            r.__enter__.return_value = io.BytesIO(
                json.dumps({"totalRecords": 0, "opportunitiesData": []}).encode())
            return r

        with mock.patch.object(sd, "BASE", tmp), \
             mock.patch.dict("os.environ", {"SAM_API_KEY": "k"}), \
             mock.patch.object(sd, "http_get", side_effect=fake):
            code = sd.main(args)
        return code, urls, json.loads((tmp / "out" / "state.json").read_text())

    def _tmp(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "config.toml").write_text(
            '[search]\nnaics=["a","b","c","d","e"]\nnotice_types=["o"]\n'
            'set_asides=["VSA"]\nunspecified_setaside_ok_for=[]\nlookback_days=1\n'
            'daily_request_budget=4\nfetch_reserve=2\nprefer_states=[]\n')
        return tmp

    def test_rotation_across_runs_and_lookback_widening(self):
        tmp = self._tmp()
        _, urls, st = self._run(tmp, ["discover", "--force"])
        self.assertEqual(urls, ["a", "b"])
        self.assertEqual(st["naics_cursor"], 2)
        _, urls, st = self._run(tmp, ["discover", "--force"])
        self.assertEqual(urls, ["c", "d"])
        _, urls, st = self._run(tmp, ["discover", "--force"])
        self.assertEqual(urls, ["e", "a"])  # wraps; every code reached
        md = sorted((tmp / "out").glob("shortlist-*.md"))[0].read_text()
        self.assertIn("full rotation every 3 day(s)", md)
        self.assertIn("window 4 days", md)  # max(1, 3 + 1)

    def test_failed_code_does_not_advance_rotation(self):
        tmp = self._tmp()
        code, urls, st = self._run(tmp, ["discover", "--force"], fail_on="b")
        self.assertEqual(urls, ["a", "b"])
        self.assertEqual(st["naics_cursor"], 1)  # only "a" completed; "b" retried next run
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
