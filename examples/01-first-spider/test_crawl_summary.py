import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from crawl_summary import CrawlSummaryExtension


class FakeSpider:
    name = "catalog-test"
    logger = Mock()


class FakeStats:
    def get_stats(self):
        return {
            "item_scraped_count": 3,
            "item_dropped_count": 2,
            "response_received_count": 5,
            "finish_reason": "finished",
            "downloader/response_status_count/200": 5,
            "secret_or_unrelated_stat": "must not leak",
        }


class CrawlSummaryTests(unittest.TestCase):
    def test_writes_atomic_json_summary_with_categorized_failures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "reports" / "crawl.json"
            extension = CrawlSummaryExtension(target, FakeStats())
            extension.started_at_utc = "2026-01-01T00:00:00+00:00"
            extension.item_scraped({"title": "accepted"}, None, FakeSpider())
            extension.item_scraped({"title": "accepted too"}, None, FakeSpider())
            extension.item_dropped({}, None, Exception("duplicate product URL"), FakeSpider())
            extension.item_dropped({}, None, Exception("missing required field: title"), FakeSpider())
            extension.item_dropped({}, None, Exception("validation text mentions a duplicate but is not a duplicate"), FakeSpider())
            extension.item_error({}, None, FakeSpider(), ValueError("pipeline broke"))
            extension.spider_error(ValueError("parse broke"), None, FakeSpider())
            extension.request_dropped(Mock(), FakeSpider())

            extension.spider_closed(FakeSpider(), "finished")

            summary = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(summary["schema_version"], 1)
            self.assertEqual(summary["spider_name"], "catalog-test")
            self.assertEqual(summary["close_reason"], "finished")
            self.assertEqual(summary["stats"]["item_scraped_count"], 3)
            self.assertEqual(summary["items_scraped_signal_count"], 2)
            self.assertEqual(summary["item_drop_categories"], {
                "duplicate": 1,
                "validation_or_policy": 2,
            })
            self.assertEqual(summary["pipeline_errors_by_type"], {"ValueError": 1})
            self.assertEqual(summary["spider_errors_by_type"], {"ValueError": 1})
            self.assertEqual(summary["requests_dropped_by_scheduler"], 1)
            self.assertNotIn("secret_or_unrelated_stat", summary["stats"])
            self.assertEqual(list(target.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
