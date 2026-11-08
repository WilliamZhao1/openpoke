import io
import json
import unittest
from unittest.mock import patch

from server import observability
from server.observability import (
    Availability, EvidenceMode, Observation, ObservationReason, ObservationSource,
    record_event,
)


class ObservationEvidenceTests(unittest.TestCase):
    def test_all_four_states_and_provenance_survive_json_serialization(self):
        observations = {
            "elapsed_ms": Observation(12.5, Availability.AVAILABLE, ObservationSource.CLOCK),
            "input_tokens": Observation(
                None, Availability.UNAVAILABLE, ObservationSource.PROVIDER_USAGE,
                EvidenceMode.MOCK, ObservationReason.USAGE_MISSING,
            ),
            "output_tokens": Observation(0, Availability.AVAILABLE, ObservationSource.PROVIDER_USAGE, EvidenceMode.MOCK),
            "failure_category": Observation(
                None, Availability.NOT_APPLICABLE, ObservationSource.RUNTIME,
                reason=ObservationReason.NO_FAILURE,
            ),
            "usage_complete": Observation(
                False, Availability.INFERRED, ObservationSource.DERIVED,
                evidence=("input_tokens", "output_tokens"),
            ),
            "prompt": Observation("private prompt", Availability.AVAILABLE, ObservationSource.RUNTIME),
        }
        with self.assertLogs("openpoke.server", level="INFO") as captured:
            record_event("test", component="test", outcome="succeeded", observations=observations, retrieval_status="partial")
        stored = json.loads(captured.records[0].getMessage().removeprefix("telemetry "))
        self.assertEqual(stored["schema_version"], 2)
        states = {item["availability"] for item in stored["observations"].values()}
        self.assertEqual(states, {"available", "inferred", "unavailable", "not_applicable"})
        self.assertIsNone(stored["input_tokens"])
        self.assertEqual(stored["output_tokens"], 0)
        self.assertFalse(stored["usage_complete"])
        self.assertEqual(stored["observations"]["usage_complete"]["evidence"], ["input_tokens", "output_tokens"])
        self.assertEqual(stored["observations"]["input_tokens"]["source_mode"], "mock")
        self.assertEqual(stored["observations"]["elapsed_ms"]["source_mode"], "local")
        self.assertNotIn("retrieval_status", stored)
        self.assertNotIn("private", json.dumps(stored))

    def test_invalid_states_reasons_and_unsupported_inferences_are_rejected(self):
        cases = [
            {"value": None, "availability": Availability.AVAILABLE},
            {"value": 0, "availability": Availability.UNAVAILABLE, "reason": ObservationReason.USAGE_MISSING},
            {"value": None, "availability": Availability.NOT_APPLICABLE},
            {"value": 0, "availability": Availability.AVAILABLE, "reason": ObservationReason.NOT_RECORDED},
            {"value": False, "availability": Availability.INFERRED},
            {"value": False, "availability": Availability.INFERRED, "source": ObservationSource.DERIVED},
            {"value": False, "availability": Availability.INFERRED, "source": ObservationSource.DERIVED, "evidence": ("private text",)},
            {"value": None, "availability": Availability.UNAVAILABLE, "reason": "private error message"},
            {"value": 1, "availability": "unknown"},
            {"value": float("nan"), "availability": Availability.AVAILABLE},
            {"value": 1, "availability": Availability.AVAILABLE, "source": ObservationSource.PROVIDER_USAGE},
        ]
        for fields in cases:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    Observation(**{"source": ObservationSource.RUNTIME, **fields})

    def test_dangling_evidence_is_not_emitted_and_an_unknown_failure_is_not_inapplicable(self):
        inferred = Observation(
            False, Availability.INFERRED, ObservationSource.DERIVED,
            evidence=("input_tokens", "output_tokens"),
        )
        with (
            patch.object(observability.logger, "info") as sink,
            patch.object(observability.sys, "stderr", new_callable=io.StringIO) as fallback,
        ):
            record_event("test", component="test", observations={"usage_complete": inferred})
        sink.assert_not_called()
        self.assertEqual(fallback.getvalue(), "OpenPoke telemetry emission failed\n")
        with self.assertLogs("openpoke.server", level="INFO") as captured:
            record_event("test", component="test", outcome="failed", failure_category=None)
        observed = captured.records[0].telemetry["observations"]["failure_category"]
        self.assertEqual(observed["availability"], "unavailable")
        self.assertEqual(observed["reason"], "not_recorded")


if __name__ == "__main__":
    unittest.main()
