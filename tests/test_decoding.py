from __future__ import annotations

import unittest

from werkzeug.datastructures import ImmutableMultiDict

from flask_typescript.utils import dedottify
from flask_typescript.utils import jquery_form
from flask_typescript.utils import unflatten


class TestDecondig(unittest.TestCase):
    def test_JQueryForm(self):
        """Test jQuery decoding"""
        data = ImmutableMultiDict([("extra[0][query]", "a"), ("extra[1][query]", "b")])
        json = jquery_form(data)

        self.assertEqual(json, dict(extra=[dict(query="a"), dict(query="b")]))

    def test_Unflatten(self):
        """Test Unflatten"""
        data = ImmutableMultiDict([("a", "a"), ("a", "b"), ("a", "c")])
        json = unflatten(data)

        self.assertEqual(json, dict(a=["a", "b", "c"]))

    def test_Dedottify(self):
        """Test detottify"""
        data = ImmutableMultiDict(
            [("a.a", "a"), ("a.b", "b"), ("a.c", "c"), ("a.b", "1")],
        )
        json = dedottify(unflatten(data))

        self.assertEqual(json, dict(a={"a": "a", "b": ["b", "1"], "c": "c"}))
