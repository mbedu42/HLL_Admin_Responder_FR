import unittest
from datetime import datetime, timezone

from discord_bot.bot import PARIS_TIMEZONE, format_paris_datetime


class DiscordTimeTests(unittest.TestCase):
    def test_formats_summer_utc_time_as_paris_daylight_time(self):
        value = datetime(2026, 8, 18, 12, 28, tzinfo=timezone.utc)

        self.assertEqual(format_paris_datetime(value), "2026-08-18 14:28")

    def test_formats_winter_utc_time_as_paris_standard_time(self):
        value = datetime(2026, 1, 18, 12, 28, tzinfo=timezone.utc)

        self.assertEqual(format_paris_datetime(value), "2026-01-18 13:28")

    def test_treats_naive_crcon_iso_time_as_utc(self):
        self.assertEqual(
            format_paris_datetime("2026-08-18T12:28:00"),
            "2026-08-18 14:28",
        )

    def test_preserves_an_unrecognized_crcon_time(self):
        self.assertEqual(format_paris_datetime("now"), "now")

    def test_paris_timezone_has_the_expected_name(self):
        self.assertEqual(PARIS_TIMEZONE.key, "Europe/Paris")


if __name__ == "__main__":
    unittest.main()
