from __future__ import annotations

import unittest

from pydantic import BaseModel

from flask_typescript.api import converter
from flask_typescript.api import MISSING


class LinkedList(BaseModel):
    val: int
    next: LinkedList | None = None


class TestConverters(unittest.TestCase):
    def test_LinkedList(self):
        """Test recursive Model"""
        cvt = converter(LinkedList)

        ll = cvt(dict(val=0, next=dict(val=1, next=dict(val=3))))
        self.assertTrue(ll is not MISSING)
        self.assertEqual(ll.next.next.val, 3)
