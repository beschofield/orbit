#!/usr/bin/env python3
"""Test fixture: `orbit ping` emits ping.sent; received pings are counted in the prompt."""
import json
import sys

inp = json.load(sys.stdin)
if inp["trigger"]["kind"] == "command":
    print(json.dumps({"emit": [{"type": "ping.sent", "data": {}}], "print": "ping!"}))
else:
    n = sum(1 for e in inp["events"] if e["origin"] == inp["peer"]["name"] and e["type"] == "ping.sent")
    print(json.dumps({"prompt": f"got {n}"}))
