from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy


class SQLA(SQLAlchemy):
    def register_metadata(self, namespace):
        if "__bind_key__" in namespace and "metadata" not in namespace:
            key = namespace.pop("__bind_key__")
            namespace["metadata"] = self._make_metadata(key)
