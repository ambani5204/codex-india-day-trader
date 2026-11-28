"""Security contract (Phase 2): read-only market data, fail-closed order gates,
no hardcoded secrets. Scans the live source tree."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = list((ROOT / "india_trader").glob("*.py")) + list((ROOT / "deploy").glob("*.py"))


class SecurityContract(unittest.TestCase):
    def test_upstox_adapter_is_get_only(self):
        src = (ROOT / "india_trader" / "upstox.py").read_text()
        self.assertIn("method='GET'", src.replace('"', "'"))
        # no write verbs / order endpoints in the market-data adapter
        for forbidden in ("method='POST'", "method='PUT'", "method='DELETE'", "/order", "place_order"):
            self.assertNotIn(forbidden, src.replace('"', "'"), f"upstox.py must not contain {forbidden}")

    def test_no_order_placement_anywhere(self):
        for f in SRC:
            txt = f.read_text()
            for pat in ("place_order(", "placeOrder", "/order/place", "/v2/order", "/v3/order"):
                self.assertNotIn(pat, txt, f"{f.name} must not place orders ({pat})")

    def test_live_session_forces_orders_disabled(self):
        src = (ROOT / "deploy" / "cloud_paper_session.py").read_text()
        self.assertIn("allow_live_orders=False", src.replace(" ", ""))

    def test_no_hardcoded_long_token_literals(self):
        # access_token / api_key / secret assigned a long string literal in source
        pat = re.compile(r"(access_token|api_key|secret|password)\s*=\s*['\"][A-Za-z0-9_\-\.]{20,}['\"]", re.I)
        for f in SRC:
            m = pat.search(f.read_text())
            self.assertIsNone(m, f"{f.name} may contain a hardcoded secret: {m.group(0)[:30] if m else ''}")


if __name__ == "__main__":
    unittest.main()
