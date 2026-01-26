# Copyright (c) 2020-2026 CRS4
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Union

from flask_sqlalchemy import Pagination
from sqlalchemy import VARCHAR, inspect, types

from lifemonitor.cache import CacheMixin
from lifemonitor.db import db

logger = logging.getLogger(__name__)


class PaginationInfo:
    def __init__(self, page: int, per_page: int, max_items: Optional[int] = None):
        self.page = page
        self.per_page = per_page
        self.max_items = max_items
        self._data: Union[Pagination, List] = None
        self._total_items: Optional[int] = None

    @property
    def data(self) -> Union[Pagination, List]:
        return self._data

    @data.setter
    def data(self, value: Union[Pagination, List]):
        self._data = value

    @property
    def total_items(self) -> int:
        """
        Get the total number of items.
        If the total number of items has been explicitly set, it returns that value.
        If the data is a Pagination object, it returns the total from that object.
        If the data is a list, it returns the length of the list.
        If none of the above conditions are met, it returns 0.

        Returns:
            int: The total number of items.
        """
        if self._total_items is not None:
            return self._total_items
        if isinstance(self._data, Pagination):
            return self._data.total
        elif isinstance(self._data, list):
            return len(self._data)
        else:
            return 0

    @property
    def total_pages(self) -> int:
        """
        Calculate the total number of pages based on items per page.

        Returns the total number of pages by dividing the total number of items
        by the number of items per page. If items per page is 0, returns 0 to
        avoid division by zero.

        Returns:
            int: The total number of pages. If items per page is 0, returns 0;
                 otherwise returns (total_items + per_page - 1) // per_page (integer division).
        """
        if not self.per_page or self.per_page == 0:
            return 0
        return (self.total_items + (self.per_page - 1)) // self.per_page


class PageableMixin:
    @classmethod
    def paginate_query(cls, query, page: PaginationInfo):
        """ Paginate a query
        :param query: The query to paginate
        :param page: The page number (1-based)
        :param per_page: The number of items per page
        :param max_per_page: The maximum number of items per page
        :return: A list of items for the requested page
        """
        pagination = query.paginate(
            page=page.page,
            per_page=page.per_page,
            max_per_page=page.max_items,
            error_out=False
        )
        page.data = pagination
        page.per_page = pagination.per_page
        page.max_items = pagination.total
        return pagination.items

    @classmethod
    def paginate_list(cls, items: List, page: PaginationInfo):
        """ Paginate a list of items
        :param items: The list of items to paginate
        :param page: The page number. The first page is 0.
        :param per_page: The number of items per page
        :param max_per_page: The maximum number of items per page
        :return: A list of items for the requested page
        """
        # default per_page to the length of items
        per_page = len(items)
        # choose per_page safely only when values are provided
        if page.per_page and page.per_page > 0:
            per_page = min(page.per_page, len(items))
        # Compute start and end indices
        start = (page.page - 1) * per_page
        end = start + per_page
        # Adjust end index if max_items is set
        if page.max_items is not None:
            end = min(end, page.max_items)
        # Slice the list to get the paginated items
        paginated_items = items[start:end]
        # Set pagination data
        page.per_page = per_page
        page.data = paginated_items
        page._total_items = len(items)
        # Return the paginated items
        return paginated_items


class ModelMixin(CacheMixin, PageableMixin):

    def refresh(self, **kwargs):
        db.session.refresh(self, **kwargs)

    def save(self, commit: bool = True, flush: bool = True, update_modified: bool = True):
        if hasattr(self, 'modified') and update_modified:
            setattr(self, 'modified', datetime.now(tz=timezone.utc))
        with db.session.begin_nested():
            db.session.add(self)
        if commit:
            db.session.commit()
        if flush:
            db.session.flush()

    def delete(self, commit: bool = True, flush: bool = True):
        with db.session.begin_nested():
            db.session.delete(self)
        if commit:
            db.session.commit()
        if flush:
            db.session.flush()

    def detach(self):
        db.session.expunge(self)

    @property
    def _object_state(self):
        return inspect(self)

    def is_transient(self) -> bool:
        return self._object_state.transient

    def is_pending(self) -> bool:
        return self._object_state.pending

    def is_detached(self) -> bool:
        return self._object_state.detached

    def is_persistent(self) -> bool:
        return self._object_state.persistent

    @classmethod
    def all(cls) -> List:
        return cls.query.all()


class UUID(types.TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's UUID type, otherwise uses
    CHAR(32), storing as stringified hex values.

    """
    impl = types.CHAR
    cache_ok = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import UUID as _UUID
            return dialect.type_descriptor(_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(types.CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % uuid.UUID(value).int
            else:
                # hexstring
                return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(value)
            return value


class JSON(types.TypeDecorator):
    """Platform-independent JSON type.

    Uses PostgreSQL's JSONB type,
    otherwise uses the standard JSON

    """
    impl = types.JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import JSONB
            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(types.JSON())

    def coerce_compared_value(self, op, value):
        return self.impl.coerce_compared_value(op, value)


class CustomSet(types.TypeDecorator):
    """Represents an immutable structure as a json-encoded string."""
    impl = VARCHAR

    def process_bind_param(self, value, dialect):
        if value is not None:
            if not isinstance(value, set):
                raise ValueError("Invalid value type. Got %r", type(value))
            value = ",".join(value)
        return value

    def process_result_value(self, value, dialect):
        return set() if value is None or len(value) == 0 \
            else set(value.split(','))


class StringSet(CustomSet):
    """Represents an immutable structure as a json-encoded string."""
    pass


class IntegerSet(CustomSet):
    """Represents an immutable structure as a json-encoded string."""

    def process_bind_param(self, value, dialect):
        if value is not None:
            if not isinstance(value, set):
                raise ValueError("Invalid value type. Got %r", type(value))
            value = ",".join([str(_) for _ in value])
        return value

    def process_result_value(self, value, dialect):
        return set() if value is None or len(value) == 0 \
            else set({int(_) for _ in value.split(',')})
