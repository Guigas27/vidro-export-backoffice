import math
from dataclasses import dataclass
from typing import List


@dataclass
class Page:
    items: List
    page: int
    per_page: int
    total: int

    @property
    def pages(self):
        return max(1, math.ceil(self.total / self.per_page))

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages


def paginate(rows, page=1, per_page=15):
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    total = len(rows)
    pages = max(1, math.ceil(total / per_page))
    page = min(page, pages)
    start = (page - 1) * per_page
    return Page(rows[start:start + per_page], page, per_page, total)
