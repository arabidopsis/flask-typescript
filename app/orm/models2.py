from __future__ import annotations

import enum
from datetime import datetime
from typing import Annotated
from typing import get_args
from typing import Literal

from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.mysql import SET
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.orm import foreign
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.types import Enum
from typing_extensions import TypedDict

from flask_typescript.orm.meta import BaseDC as Base


class Locs(enum.Enum):
    mito = "mito"
    plastid = "plastid"


values = Literal["mito", "plastid"]
locs = get_args(values)
myset = set[values]


class Author(TypedDict):
    name: str


pubmed = Annotated[str, mapped_column(VARCHAR(19, charset="latin1"))]
locus = Annotated[str | None, mapped_column(String(32))]

# type_annotation_map = {
#     pubmed: VARCHAR(19, charset="latin1") # (19)

# }
# https://docs.sqlalchemy.org/en/20/orm/dataclasses.html#integration-with-annotated
# Base.registry.update_type_annotation_map(type_annotation_map)


class Attachment(Base):
    __tablename__ = "attachment"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    pubmed: Mapped[pubmed] = mapped_column()
    name: Mapped[str | None] = mapped_column(String(128))

    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        init=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    paper: Mapped[Paper] = relationship(
        lambda: Paper,
        primaryjoin=lambda: foreign(Attachment.pubmed) == Paper.pubmed,
        back_populates="attachments",
    )


class Location(Base):
    __tablename__ = "location"
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    pubmed: Mapped[pubmed] = mapped_column(index=True)
    locus: Mapped[locus] = mapped_column(nullable=False)
    # location: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[set[values]] = mapped_column(SET(*get_args(values)))
    location2: Mapped[Locs] = mapped_column(Enum(Locs))

    paper: Mapped[Paper] = relationship(
        lambda: Paper,
        primaryjoin=lambda: foreign(Location.pubmed) == Paper.pubmed,
        back_populates="locations",
        default=None,
    )


class Paper(Base):
    __tablename__ = "paper"
    pubmed: Mapped[pubmed] = mapped_column(primary_key=True)
    abstract: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[Author]] = mapped_column(JSON)
    some: Mapped[int] = mapped_column(Integer)

    attachments: Mapped[list[Attachment]] = relationship(
        Attachment,
        primaryjoin=lambda: foreign(Attachment.pubmed) == Paper.pubmed,
        back_populates="paper",
        default_factory=list,
    )

    locations: Mapped[list[Location]] = relationship(
        Location,
        primaryjoin=lambda: foreign(Location.pubmed) == Paper.pubmed,
        back_populates="paper",
        default_factory=list,
    )
