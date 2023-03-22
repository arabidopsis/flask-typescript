from __future__ import annotations

import unittest

from werkzeug.datastructures import ImmutableMultiDict


class TestFlask(unittest.TestCase):
    def setUp(self):
        from .app import app

        self.app = app
        self.client = app.test_client()

    # def test_Flask(self):
    #     from .app import Arg5
    #     with self.client:
    #         response = self.client.get('/qqq', data={
    #             'a':'5', 'b':'44'
    #         })
    #     self.assertEqual(response.status_code, 200)
    #     self.assertTrue(response.is_json)
    #     self.assertEqual(Arg5(**response.json), Arg5(query='5-44'))

    def test_List(self):
        """Flask list as JSON"""
        from .app import Arg5

        # data=ImmutableMultiDict([('extra.query','a'), ('extra.query', 'b')])
        with self.client:
            response = self.client.post(
                "/arg5",
                json={
                    "extra": [{"query": "a"}, {"query": "b"}],
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertEqual(Arg5(**response.json), Arg5(query="a"))

    def test_FormList(self):
        """Flask list as jQuery FormData"""
        from .app import Arg5

        data = ImmutableMultiDict([("extra[0][query]", "a"), ("extra[1][query]", "b")])
        with self.client:
            response = self.client.post("/arg6", data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertEqual(Arg5(**response.json), Arg5(query="a"))
