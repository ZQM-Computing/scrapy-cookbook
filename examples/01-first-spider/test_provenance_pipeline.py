import unittest
from datetime import datetime

from provenance_pipeline import ProvenancePipeline


class FakeSpider:
    name = "catalog-test"


class ProvenancePipelineTests(unittest.TestCase):
    def test_adds_utc_timestamp_and_spider_without_changing_source_fields(self):
        item = {
            "title": "A Sample Book",
            "url": "https://example.com/book",
            "source_url": "https://example.com/catalog",
            "price_text": "£12.34",
        }
        result = ProvenancePipeline().process_item(item, FakeSpider())
        self.assertIs(result, item)
        self.assertEqual(result["spider_name"], "catalog-test")
        timestamp = datetime.fromisoformat(result["extracted_at_utc"])
        self.assertIsNotNone(timestamp.tzinfo)
        self.assertEqual(timestamp.utcoffset().total_seconds(), 0)
        self.assertEqual(result["source_url"], "https://example.com/catalog")
        self.assertEqual(result["url"], "https://example.com/book")


if __name__ == "__main__":
    unittest.main()
