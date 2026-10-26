import unittest

from scrapy.http import HtmlResponse, Request

from spider import CatalogSpider


class CatalogSpiderTests(unittest.TestCase):
    def setUp(self):
        self.spider = CatalogSpider()
        self.url = "https://books.toscrape.com/catalogue/category/books_1/index.html"

    def response(self, body):
        request = Request(self.url)
        return HtmlResponse(url=self.url, request=request, body=body, encoding="utf-8")

    def test_extracts_complete_product_and_resolves_relative_url(self):
        response = self.response("""
            <html><body>
              <article class="product_pod">
                <h3><a href="../../../the-book_1/index.html" title="A Sample Book">A Sample Book</a></h3>
                <p class="price_color">£12.34</p>
              </article>
              <li class="next"><a href="page-2.html">next</a></li>
            </body></html>
        """)

        results = list(self.spider.parse(response))
        item = next(result for result in results if isinstance(result, dict))
        next_request = next(result for result in results if isinstance(result, Request))

        self.assertEqual(item["title"], "A Sample Book")
        self.assertEqual(item["price_text"], "£12.34")
        self.assertEqual(
            item["url"],
            "https://books.toscrape.com/catalogue/the-book_1/index.html",
        )
        self.assertEqual(item["source_url"], self.url)
        self.assertEqual(next_request.url, "https://books.toscrape.com/catalogue/category/books_1/page-2.html")

    def test_skips_incomplete_product_records(self):
        response = self.response("""
            <article class="product_pod">
              <h3><a href="/incomplete.html" title="No price">No price</a></h3>
            </article>
        """)
        self.assertEqual(list(self.spider.parse(response)), [])

    def test_spider_has_polite_bounded_settings(self):
        settings = CatalogSpider.custom_settings
        self.assertTrue(settings["ROBOTSTXT_OBEY"])
        self.assertEqual(settings["DOWNLOAD_DELAY"], 1.0)
        self.assertEqual(settings["CONCURRENT_REQUESTS_PER_DOMAIN"], 1)
        self.assertTrue(settings["AUTOTHROTTLE_ENABLED"])
        self.assertEqual(settings["CLOSESPIDER_PAGECOUNT"], 5)


if __name__ == "__main__":
    unittest.main()
