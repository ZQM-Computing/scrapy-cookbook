"""Add reproducible extraction provenance without overwriting source fields."""
from datetime import datetime, timezone

from itemadapter import ItemAdapter


class ProvenancePipeline:
    """Attach crawl time and spider identity to every accepted candidate item."""

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        adapter["extracted_at_utc"] = datetime.now(timezone.utc).isoformat()
        adapter["spider_name"] = spider.name
        return item
