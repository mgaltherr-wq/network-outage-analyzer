import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.history import DAY, HOUR, HistoryStore

# A fixed UTC midnight, so hour/day bucket boundaries are predictable.
T0 = 1_790_000_000 // DAY * DAY


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.store = HistoryStore(Path(temp_dir.name) / "history.db")
        self.addCleanup(self.store.close)

    def test_sweeps_roll_up_into_hourly_availability(self):
        locations = {"10.0.0.1": "HQ", "10.0.0.2": "HQ"}
        self.store.record_sweep({"10.0.0.1": True, "10.0.0.2": True}, locations, T0 + 10)
        self.store.record_sweep({"10.0.0.1": True, "10.0.0.2": False}, locations, T0 + 20)
        self.store.record_sweep({"10.0.0.1": False, "10.0.0.2": False}, locations, T0 + HOUR + 5)

        trends = self.store.trends(T0, HOUR, now=T0 + 2 * HOUR)

        self.assertEqual(trends["fleet"], [
            {"t": T0, "availability": 0.75},
            {"t": T0 + HOUR, "availability": 0.0},
        ])
        self.assertAlmostEqual(trends["availability"], 3 / 6)
        self.assertEqual([loc["location"] for loc in trends["locations"]], ["HQ"])
        self.assertEqual(
            trends["devices"],
            [
                {"ip_address": "10.0.0.2", "location": "HQ", "availability": 1 / 3},
                {"ip_address": "10.0.0.1", "location": "HQ", "availability": 2 / 3},
            ],
        )

    def test_hours_with_no_data_are_omitted_not_zero(self):
        self.store.record_sweep({"10.0.0.1": True}, {}, T0)
        self.store.record_sweep({"10.0.0.1": True}, {}, T0 + 5 * HOUR)

        fleet = self.store.trends(T0, HOUR, now=T0 + 6 * HOUR)["fleet"]

        self.assertEqual([p["t"] for p in fleet], [T0, T0 + 5 * HOUR])

    def test_daily_buckets_align_to_the_viewers_utc_offset(self):
        # 23:00 and 01:00 UTC are different UTC days but the same day at UTC-5.
        self.store.record_sweep({"10.0.0.1": True}, {}, T0 - HOUR)
        self.store.record_sweep({"10.0.0.1": False}, {}, T0 + HOUR)

        utc = self.store.trends(T0 - DAY, DAY, now=T0 + DAY)["fleet"]
        eastern = self.store.trends(T0 - DAY, DAY, now=T0 + DAY, utc_offset_seconds=-5 * HOUR)["fleet"]

        self.assertEqual(len(utc), 2)
        self.assertEqual(eastern, [{"t": T0 - DAY + 5 * HOUR, "availability": 0.5}])

    def test_outage_episode_opens_extends_and_closes(self):
        self.store.update_outages({"HQ": (1.0, 4)}, 0.9, T0)
        self.store.update_outages({"hq": (0.95, 4)}, 0.9, T0 + 60)
        ongoing = self.store.trends(T0 - HOUR, HOUR, now=T0 + 90)["outages"]
        self.store.update_outages({"HQ": (0.25, 4)}, 0.9, T0 + 120)
        closed = self.store.trends(T0 - HOUR, HOUR, now=T0 + 600)["outages"]

        self.assertEqual(len(ongoing), 1)
        self.assertTrue(ongoing[0]["ongoing"])
        self.assertEqual(ongoing[0]["duration_seconds"], 90)
        self.assertEqual(closed, [{
            "location": "HQ",
            "started_at": T0,
            "ended_at": T0 + 120,
            "ongoing": False,
            "duration_seconds": 120,
            "devices": 4,
            "peak_percent_down": 1.0,
            "confidence": None,
            "ticket": None,
        }])

    def test_location_that_disappears_closes_its_episode(self):
        self.store.update_outages({"HQ": (1.0, 2)}, 0.9, T0)
        self.store.update_outages({}, 0.9, T0 + 30)

        [episode] = self.store.trends(T0 - HOUR, HOUR, now=T0 + 60)["outages"]
        self.assertEqual(episode["ended_at"], T0 + 30)

    def test_stale_episodes_close_at_last_seen_and_reopen_fresh(self):
        self.store.update_outages({"HQ": (1.0, 2)}, 0.9, T0)
        self.store.update_outages({"HQ": (1.0, 2)}, 0.9, T0 + 30)
        self.store.close_stale_episodes()  # app restarted
        self.store.update_outages({"HQ": (1.0, 2)}, 0.9, T0 + 600)

        episodes = self.store.trends(T0 - HOUR, HOUR, now=T0 + 700)["outages"]
        self.assertEqual([(e["started_at"], e["ended_at"]) for e in episodes], [
            (T0 + 600, None),
            (T0, T0 + 30),
        ])

    def test_annotate_outage_records_cause_and_first_ticket(self):
        confidence = {"weather": {"confidence": "High", "detail": "Storm"}}
        self.store.update_outages({"HQ": (1.0, 2)}, 0.9, T0)
        self.store.annotate_outage("hq", confidence, {"number": "INC001", "action": "created"})
        self.store.annotate_outage("HQ", None, {"number": "INC999", "action": "updated"})

        [episode] = self.store.trends(T0 - HOUR, HOUR, now=T0 + 60)["outages"]
        self.assertEqual(episode["confidence"], confidence)
        self.assertEqual(episode["ticket"], {"number": "INC001", "action": "created"})

    def test_location_rows_include_outage_counts(self):
        self.store.record_sweep({"10.0.0.1": False}, {"10.0.0.1": "HQ"}, T0)
        self.store.record_sweep({"10.0.0.2": True}, {"10.0.0.2": "Branch"}, T0)
        self.store.update_outages({"HQ": (1.0, 1)}, 0.9, T0)
        self.store.update_outages({"HQ": (0.0, 1)}, 0.9, T0 + 300)

        rows = self.store.trends(T0, HOUR, now=T0 + HOUR)["locations"]

        self.assertEqual(
            [(r["location"], r["availability"], r["outages"], r["outage_seconds"]) for r in rows],
            [("HQ", 0.0, 1, 300), ("Branch", 1.0, 0, 0)],
        )

    def test_prune_drops_old_rows_but_keeps_ongoing_outages(self):
        self.store.record_sweep({"10.0.0.1": True}, {}, T0)
        self.store.update_outages({"Old": (1.0, 1)}, 0.9, T0)
        self.store.update_outages({"Old": (0.0, 1)}, 0.9, T0 + 60)
        self.store.update_outages({"Ongoing": (1.0, 1)}, 0.9, T0 + 60)
        self.store.record_sweep({"10.0.0.1": True}, {}, T0 + 10 * DAY)

        self.store.prune(retention_days=5, now=T0 + 10 * DAY)

        trends = self.store.trends(0, DAY, now=T0 + 10 * DAY)
        self.assertEqual([p["t"] for p in trends["fleet"]], [T0 + 10 * DAY])
        self.assertEqual([e["location"] for e in trends["outages"]], ["Ongoing"])


if __name__ == "__main__":
    unittest.main()
