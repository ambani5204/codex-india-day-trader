"""Offline test: Firestore type mapping stores keys/types only, never values."""
import unittest

from deploy.phase0_firestore_readonly_probe import merge_types, type_summary


class Phase0FirestoreProbeTests(unittest.TestCase):
    def test_types_not_values_ever_returned(self):
        private_value = "SHOULD_NEVER_APPEAR_IN_REPORT"
        row = {
            "net_pnl": {"doubleValue": 12345.67},
            "run_id": {"stringValue": private_value},
            "closed_trades": {"integerValue": "3"},
            "optional": {"nullValue": None},
        }
        result = type_summary(row)
        self.assertEqual(result, {
            "net_pnl": ["doubleValue"],
            "run_id": ["stringValue"],
            "closed_trades": ["integerValue"],
            "optional": ["nullValue"],
        })
        self.assertNotIn(private_value, repr(result))
        self.assertNotIn("12345.67", repr(result))

    def test_multiple_observed_types_are_not_silently_coerced(self):
        found = {}
        merge_types(found, {"net_pnl": {"doubleValue": 1.5}})
        merge_types(found, {"net_pnl": {"nullValue": None}})
        self.assertEqual(found["net_pnl"], {"doubleValue", "nullValue"})

    def test_unrecognized_payload_fails_open_to_unknown_not_zero(self):
        self.assertEqual(type_summary({"unknown": {"customValue": "x"}}),
                         {"unknown": ["UNRECOGNIZED"]})


if __name__ == "__main__":
    unittest.main()
