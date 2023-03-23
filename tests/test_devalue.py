from __future__ import annotations

import re
import unittest
from datetime import datetime

from flask_typescript.devalue.parse import parse

# see https://svelte.dev/repl/138d70def7a748ce9eda736ef1c71239?version=3.49.0
# for the generation of these strings.


class TestDeValue(unittest.TestCase):
    def test_DevalueParse(self):
        """general devalue parsing"""
        s = '[{"s":1,"y":2,"q":5,"z":8,"x":6,"today":11,"pattern":12},"a simple string",[3,4],"Date","2023-03-20T09:15:38.137Z",["null","a",6,"b",7],1,"ssss",[6,9,10],2,3,["Date","2023-03-20T13:06:38.781Z"],["RegExp","potato","i"]]'
        json = parse(s)
        q = {"a": 1, "b": "ssss"}
        data = {
            "s": "a simple string",
            "y": ["Date", "2023-03-20T09:15:38.137Z"],
            "q": q,
            "z": [1, 2, 3],
            "x": 1,
            "today": datetime.fromisoformat("2023-03-20T13:06:38.781Z"),
            "pattern": re.compile("potato", re.I),
        }
        self.assertEqual(json, data)

    def test_Map(self):
        """devalue parse Map"""
        s = '[{"map":1},["Map",2,3,4,5],1,2,3,4]'
        json = parse(s)
        map = {1: 2, 3: 4}
        data = {"map": map}
        self.assertEqual(json, data)

    def test_InvalidKey(self):
        """javascript Map allows for keys like [1,2]"""
        # possibly pretty useless since you after serialization->deserialisation
        # it will be inaccessible....
        s = '[{"map":1},["Map",2,3,4,5,6,8],["Date","2023-03-22T07:58:46.900Z"],2,3,4,[7,3],1,7]'

        with self.assertRaises(ValueError) as e:
            _ = parse(s)
        self.assertEqual(e.exception.args[0], "Invalid key for Map: [1, 2]")
        # map = {datetime.fromisoformat("2023-03-22T07:55:23.304Z"): 2, (1,2):7}
        # data = {"map": map}
        # self.assertEqual(json, data)

    def test_BigInt(self):
        """See if BigInt works"""
        # javascript big int: 14342153999777412545123n
        s = '[{"big":1,"myset":2,"a":3},["BigInt","14342153999777412545123"],["Set",3,4,5,6,7],1,2,3,4,5]'
        json = parse(s)
        myset = {1, 2, 3, 4, 5}
        data = {"big": 14342153999777412545123, "myset": myset, "a": 1}
        self.assertEqual(json, data)

    def test_Infinity(self):
        """See if Infinity works"""
        import math

        s = '[{"inf":-4,"neginf":-5,"isnan":-3}]'
        json = parse(s)
        data = {"inf": math.inf, "neginf": -math.inf, "isnan": math.nan}
        self.assertEqual(json, data)

    def test_Rubbish(self):
        """See if Rubbish data works"""

        s = '[{"big":1,"myset":2,"a":3},["BigInt","14342153999777412545123"],["Set",3,4,5,6,7],1,3,4,5]'

        with self.assertRaises(IndexError) as e:
            _ = parse(s)
        self.assertEqual(e.exception.args[0], "list index out of range")
