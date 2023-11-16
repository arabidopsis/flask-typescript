from __future__ import annotations

import enum
from datetime import datetime
from typing import Annotated
from typing import get_args
from typing import Literal
from typing import TypedDict

from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.mysql import SET
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.orm import declared_attr
from sqlalchemy.orm import foreign
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.types import Enum

from flask_typescript.orm.meta import BaseDC as Base


# pylint: disable=no-self-argument
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
    __abstract__ = True
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    pubmed: Mapped[pubmed] = mapped_column()
    name: Mapped[str | None] = mapped_column(String(128))

    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        init=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    @declared_attr
    def paper(cls) -> Mapped[Paper]:
        return relationship(
            lambda: Paper,
            primaryjoin=lambda: foreign(Attachment.pubmed) == Paper.pubmed,
            back_populates="attachments",
            default=None,
        )


class Location(Base):
    __abstract__ = True
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    pubmed: Mapped[pubmed] = mapped_column(index=True)
    locus: Mapped[locus] = mapped_column(nullable=False)
    # location: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[set[values]] = mapped_column(SET(*get_args(values)))
    location2: Mapped[Locs] = mapped_column(Enum(Locs))

    @declared_attr
    def paper(cls) -> Mapped[Paper]:
        return relationship(
            Paper,
            primaryjoin=foreign(Location.pubmed) == Paper.pubmed,
            back_populates="locations",
            default=None,
        )

    # paper : Mapped[Paper] = relationship(
    #         lambda:Paper,
    #         primaryjoin=lambda: foreign(Location.pubmed) == Paper.pubmed,
    #         back_populates="locations",default=None
    #     )


class Paper(Base):
    __abstract__ = True
    pubmed: Mapped[pubmed] = mapped_column(primary_key=True)
    abstract: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[Author]] = mapped_column(JSON)
    some: Mapped[int] = mapped_column(Integer)

    @declared_attr
    def attachments(cls) -> Mapped[list[Attachment]]:
        return relationship(
            Attachment,
            primaryjoin=foreign(Attachment.pubmed) == Paper.pubmed,
            back_populates="paper",
            default_factory=list,
        )

    @declared_attr
    def locations(cls) -> Mapped[list[Location]]:
        return relationship(
            Location,
            primaryjoin=foreign(Location.pubmed) == Paper.pubmed,
            back_populates="paper",
            default_factory=list,
        )


def orm(
    papers: str,
    attachment: str,
    location: str,
    schema: str | None = None,
) -> tuple[type[Paper], type[Attachment], type[Location]]:
    table_args = {"schema": schema}

    class ORMPaper(Paper):
        __tablename__ = papers
        __clsname__ = papers.title()
        __table_args__ = table_args

        @declared_attr
        def attachments(cls) -> Mapped[list[Attachment]]:
            return relationship(
                lambda: ORMAttachment,
                primaryjoin=lambda: foreign(ORMAttachment.pubmed) == ORMPaper.pubmed,
                back_populates="paper",
                default_factory=list,
            )

        @declared_attr
        def locations(cls) -> Mapped[list[Location]]:
            return relationship(
                lambda: ORMLocation,
                primaryjoin=lambda: foreign(ORMLocation.pubmed) == ORMPaper.pubmed,
                back_populates="paper",
                default_factory=list,
            )

    class ORMAttachment(Attachment):
        __tablename__ = attachment
        __clsname__ = attachment.title()
        __table_args__ = table_args

        @declared_attr
        def paper(cls) -> Mapped[Paper]:
            return relationship(
                lambda: ORMPaper,
                primaryjoin=lambda: foreign(ORMAttachment.pubmed) == ORMPaper.pubmed,
                back_populates="attachments",
                default=None,
            )

    class ORMLocation(Location):
        __tablename__ = location
        __clsname__ = location.title()
        __table_args__ = table_args

        @declared_attr
        def paper(cls) -> Mapped[Paper]:
            return relationship(
                lambda: ORMPaper,
                primaryjoin=lambda: foreign(ORMLocation.pubmed) == ORMPaper.pubmed,
                back_populates="locations",
                default=None,
            )

    return (ORMPaper, ORMAttachment, ORMLocation)


def mapped_models() -> list[type[Base]]:
    return list(orm("Paper", "Attachment", "Location"))


def test():
    from dataclasses import is_dataclass

    a, b, c = orm("a", "b", "c")
    e, f, g = orm("e", "f", "g", schema="blah")

    print(a.metadata.tables.keys())
    print(b.paper)
    print(f.paper)

    assert is_dataclass(a)
    assert is_dataclass(b)
    assert is_dataclass(c)
    assert is_dataclass(g)
    assert a.__table__.name == "a"  # type: ignore
    assert f.paper.property.mapper.class_ is e
    assert a.attachments.property.mapper.class_ is b
    assert b.paper.property.mapper.class_ is a
    assert e.attachments.property.mapper.class_ is f


if __name__ == "__main__":
    test()
