from __future__ import annotations

import unittest

from pydantic import BaseModel

from flask_typescript.api import converter
from flask_typescript.api import MISSING


class LinkedList(BaseModel):
    val: list[int]
    next: LinkedList | None = None


class M(BaseModel):
    a: list[int]


class ListOfM(BaseModel):
    i: list[M]


class TestConverters(unittest.TestCase):
    def test_LinkedList(self):
        """Test recursive Model"""
        cvt = converter(LinkedList)

        ll = cvt(dict(val=0, next=dict(val=1, next=dict(val=3))))
        self.assertTrue(ll is not MISSING)
        self.assertTrue(isinstance(ll, LinkedList))
        self.assertEqual(ll.next.next.val, [3])

    def test_ListOfPy(self):
        """Test List of pydantic values"""
        cvt = converter(ListOfM)
        json = dict(i=[dict(a=[1]), dict(a=33)])
        listofm = cvt(json)
        self.assertTrue(listofm is not MISSING)

        self.assertEqual(listofm.i[1].a, [33])
