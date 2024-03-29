from __future__ import annotations

import json
import unittest

from werkzeug.datastructures import ImmutableMultiDict


class TestFlask(unittest.TestCase):
    def setUp(self):
        from .app import app

        self.app = app
        self.client = app.test_client()

    def test_Flask(self):
        """Flask round trip"""
        from .app import Arg5

        with self.client:
            response = self.client.get(
                "/qqq",
                data={
                    "a": "5",
                    "b": "44",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertEqual(Arg5(**response.json), Arg5(query="5-44"))

    def test_List(self):
        """Flask list as JSON"""
        from .app import Arg5

        with self.client:
            response = self.client.post(
                "/arg5",
                json={
                    "extra": [{"query": "a"}, {"query": "b"}],
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertEqual(Arg5(**response.json), Arg5(query="a"))  # type: ignore

    def test_FormList(self):
        """Flask list as jQuery FormData"""
        from .app import Arg5

        data = ImmutableMultiDict([("extra[0][query]", "a"), ("extra[1][query]", "b")])
        with self.client:
            response = self.client.get("/arg6", data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertEqual(Arg5(**response.json), Arg5(query="a"))  # type: ignore

    def test_Pydantic(self):
        """test pydantic and url path argument"""
        from .app import Arg
        from datetime import date

        a = Arg(
            query="query",
            selected=[1],
            date=date.today(),
            val=4.0,
            arg5={"query": "sss"},
        )

        score = 3

        with self.client:
            response = self.client.post(
                f"/extra/{score}",
                json=json.loads(a.model_dump_json()),
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        a.selected = a.selected * score
        self.assertEqual(Arg(**response.json), a)  # type: ignore

    def test_Error(self):
        """Test Error mode"""
        with self.client:
            response = self.client.post("/error")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.is_json)
        json = response.json
        # json = {'status':400, 'error': {'message': '...'}}
        self.assertTrue("error" in json)
        self.assertTrue("status" in json)
        self.assertEqual(json["status"], 400)
        self.assertEqual(json["error"], dict(message="this has failed"))

    def test_ResultJson(self):
        """Test Result Json"""
        with self.client:
            response = self.client.get("/json2")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        json = response.json
        self.assertTrue("result" in json)
        self.assertEqual(json["type"], "success")
        result = json["result"]
        self.assertEqual(result, [dict(a=1, b=22)])

    def xxxtest_Models(self):
        from io import StringIO
        from flask_typescript.orm.orm import find_models
        from flask_typescript.orm.orm import model_ts

        with self.app.app_context():
            models = list(find_models("app.orm.models"))
            for model in models:
                out = StringIO()
                model_ts(model, out=out)
                print(out.getvalue())
