import unittest

from scrapy.exceptions import DropItem

from pipeline import ProductValidationPipeline


class ProductValidationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = ProductValidationPipeline()
        self.item = {
            "title": "A Sample Book",
            "price_text": "£12.34",
            "url": "https://books.toscrape.com/catalogue/sample.html",
            "source_url": "https://books.toscrape.com/catalogue/category/books_1/index.html",
        }
        self.spider = object()

    def test_returns_valid_item_unchanged(self):
        self.assertIs(self.pipeline.process_item(self.item, self.spider), self.item)

    def test_rejects_missing_blank_and_non_string_required_fields(self):
        for field, value in (
            ("title", ""),
            ("price_text", "   "),
            ("url", None),
            ("source_url", 42),
        ):
            with self.subTest(field=field, value=value):
                pipeline = ProductValidationPipeline()
                item = {**self.item, field: value}
                with self.assertRaisesRegex(DropItem, field):
                    pipeline.process_item(item, self.spider)

    def test_rejects_relative_non_http_and_malformed_urls(self):
        for url in (
            "/catalogue/book.html",
            "ftp://example.com/book",
            "https:///missing-host",
            "https://example.com:99999/book",
            "https://user:secret@example.com/book",
            "https://example.com/a book",
        ):
            with self.subTest(url=url):
                item = {**self.item, "url": url}
                with self.assertRaises(DropItem):
                    ProductValidationPipeline().process_item(item, self.spider)

    def test_rejects_invalid_source_url(self):
        item = {**self.item, "source_url": "javascript:alert(1)"}
        with self.assertRaisesRegex(DropItem, "source_url"):
            self.pipeline.process_item(item, self.spider)

    def test_drops_duplicate_url_after_safe_normalization(self):
        self.pipeline.process_item(self.item, self.spider)
        duplicate = {
            **self.item,
            "url": "HTTPS://BOOKS.TOSCRAPE.COM/catalogue/sample.html#details",
        }
        with self.assertRaisesRegex(DropItem, "duplicate product URL"):
            self.pipeline.process_item(duplicate, self.spider)

    def test_query_strings_remain_distinct(self):
        self.pipeline.process_item(self.item, self.spider)
        different_query = {
            **self.item,
            "url": "https://books.toscrape.com/catalogue/sample.html?edition=2",
        }
        self.assertIs(
            self.pipeline.process_item(different_query, self.spider),
            different_query,
        )

    def test_duplicate_filter_can_be_disabled_for_persistent_pipeline(self):
        pipeline = ProductValidationPipeline(deduplicate=False)
        self.assertIs(pipeline.process_item(self.item, self.spider), self.item)
        self.assertIs(pipeline.process_item(self.item, self.spider), self.item)

    def test_duplicate_state_is_instance_scoped(self):
        self.pipeline.process_item(self.item, self.spider)
        other_run = ProductValidationPipeline()
        self.assertIs(other_run.process_item(self.item, self.spider), self.item)


if __name__ == "__main__":
    unittest.main()
