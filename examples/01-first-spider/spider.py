"""A bounded, robots-respecting Scrapy example for Books to Scrape.

This is an educational demo target. Before adapting the spider, verify the
target's terms, robots.txt, access rules, and acceptable request rate.
"""
import scrapy


class CatalogSpider(scrapy.Spider):
    name = "catalog"
    allowed_domains = ["books.toscrape.com"]
    start_urls = ["https://books.toscrape.com/catalogue/category/books_1/index.html"]

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "USER_AGENT": "ZQMScrapyCookbook/1.0 (+https://github.com/ZQM-Computing/scrapy-cookbook; educational example)",
        "DOWNLOAD_DELAY": 1.0,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 1.0,
        "AUTOTHROTTLE_MAX_DELAY": 10.0,
        "CLOSESPIDER_PAGECOUNT": 5,
        "ITEM_PIPELINES": {
            "provenance_pipeline.ProvenancePipeline": 100,
            "pipeline.ProductValidationPipeline": 300,
        },
        "EXTENSIONS": {
            "crawl_summary.CrawlSummaryExtension": 500,
        },
    }

    def parse(self, response):
        """Yield complete product records and follow the next-page link."""
        for product in response.css("article.product_pod"):
            title = (product.css("h3 a::attr(title)").get() or "").strip()
            price = (product.css(".price_color::text").get() or "").strip()
            href = product.css("h3 a::attr(href)").get()

            # Avoid emitting partial records when the source markup changes.
            if not title or not price or not href:
                self.logger.warning(
                    "Skipping incomplete product record on %s", response.url
                )
                continue

            yield {
                "title": title,
                "price_text": price,
                "url": response.urljoin(href),
                "source_url": response.url,
            }

        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)
