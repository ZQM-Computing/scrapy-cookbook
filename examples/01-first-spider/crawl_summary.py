"""Optional JSON crawl summary based on Scrapy signals and collected stats."""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from scrapy import signals
from scrapy.exceptions import NotConfigured


class CrawlSummaryExtension:
    """Write an atomic machine-readable summary when CRAWL_SUMMARY_PATH is set."""

    def __init__(self, output_path, stats):
        self.output_path = Path(output_path).expanduser()
        self.stats = stats
        self.started_at_utc = None
        self.drop_reasons = Counter()
        self.pipeline_errors = Counter()
        self.spider_errors = Counter()
        self.dropped_requests = 0

    @classmethod
    def from_crawler(cls, crawler):
        output_path = crawler.settings.get("CRAWL_SUMMARY_PATH")
        if not output_path:
            raise NotConfigured("Set CRAWL_SUMMARY_PATH to enable JSON crawl summaries")
        extension = cls(output_path, crawler.stats)
        crawler.signals.connect(extension.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(extension.item_dropped, signal=signals.item_dropped)
        crawler.signals.connect(extension.item_error, signal=signals.item_error)
        crawler.signals.connect(extension.spider_error, signal=signals.spider_error)
        crawler.signals.connect(extension.request_dropped, signal=signals.request_dropped)
        crawler.signals.connect(extension.spider_closed, signal=signals.spider_closed)
        return extension

    def spider_opened(self, spider):
        self.started_at_utc = datetime.now(timezone.utc).isoformat()

    def item_dropped(self, item, response, exception, spider):
        message = str(exception).lower()
        category = "duplicate" if "duplicate" in message else "validation_or_policy"
        self.drop_reasons[category] += 1

    def item_error(self, item, response, spider, failure):
        value = getattr(failure, "value", failure)
        self.pipeline_errors[type(value).__name__] += 1

    def spider_error(self, failure, response, spider):
        value = getattr(failure, "value", failure)
        self.spider_errors[type(value).__name__] += 1

    def request_dropped(self, request, spider):
        self.dropped_requests += 1

    def _summary(self, spider, reason, closed_at):
        stats = self.stats.get_stats()
        relevant_stats = {}
        prefixes = (
            "downloader/response_status_count/",
            "downloader/exception_count/",
            "spider_exceptions/",
            "item_dropped_reasons_count/",
            "log_count/",
        )
        exact = {
            "elapsed_time_seconds", "finish_reason", "finish_time",
            "item_dropped_count", "item_scraped_count", "response_received_count",
            "request_count", "start_time",
        }
        for key, value in stats.items():
            if key in exact or key.startswith(prefixes):
                if hasattr(value, "isoformat"):
                    value = value.isoformat()
                if isinstance(value, (str, int, float, bool)) or value is None:
                    relevant_stats[key] = value
                else:
                    relevant_stats[key] = str(value)
        return {
            "schema_version": 1,
            "spider_name": spider.name,
            "started_at_utc": self.started_at_utc,
            "closed_at_utc": closed_at,
            "close_reason": reason,
            "stats": relevant_stats,
            "item_drop_categories": dict(sorted(self.drop_reasons.items())),
            "pipeline_errors_by_type": dict(sorted(self.pipeline_errors.items())),
            "spider_errors_by_type": dict(sorted(self.spider_errors.items())),
            "requests_dropped_by_scheduler": self.dropped_requests,
        }

    def spider_closed(self, spider, reason):
        closed_at = datetime.now(timezone.utc).isoformat()
        summary = self._summary(spider, reason, closed_at)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.output_path.parent),
                prefix=f".{self.output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(summary, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.output_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        spider.logger.info("Wrote crawl summary to %s", self.output_path)
