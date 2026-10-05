"""Immutable native candidate input provenance, not fabricated market evidence."""
import copy
import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from decision_inputs import attach


class CandidateInputs(unittest.TestCase):
    def fixture(self):
        # SOURCE: synthetic native bar, timestamps and identity placeholders.
        original = {"venue":"Alpaca equities","symbol":"QQQ","sessionOpen":True,
            "frames":{"1m":[{"t":"2026-10-05T13:30:00Z","o":100,"h":101,"l":99,"c":100,"v":1}]},
            "expectedStarts":{"1m":[1,2]},"fetches":{"1m":{"retrievedAt":"2026-10-05T13:31:01Z"}}}
        result = {"asOf":"2026-10-05T13:31:00Z","markets":[{"venue":"Alpaca equities","symbol":"QQQ",
            "frames":{"1m":{"status":"candidate","candidate":"long"}}}]}
        return result, [original]

    def test_retained_native_inputs_and_exact_clock_allow_replay_without_revised_provider_history(self):
        with tempfile.TemporaryDirectory() as root:
            result, requested = self.fixture()
            directory = Path(root)/"inputs"
            self.assertEqual(attach(result,requested,directory,"frozen engine","actual technical identity"),1)
            proof = result["markets"][0]["frames"]["1m"]["dataEvidence"]
            path = directory/(proof["inputSha256"]+".json.gz")
            raw = gzip.decompress(path.read_bytes()); original_bytes = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),proof["inputSha256"])
            document = json.loads(raw)
            self.assertEqual(document["bars"],requested[0]["frames"]["1m"])
            self.assertEqual(document["expectedStarts"],requested[0]["expectedStarts"]["1m"])
            self.assertEqual(proof["analysisAsOf"],result["asOf"])
            self.assertEqual(proof["frameFetchRetrievedAt"],requested[0]["fetches"]["1m"]["retrievedAt"])
            attach(result,requested,directory,"frozen engine","actual technical identity")
            self.assertEqual(path.read_bytes(),original_bytes)
            requested[0]["frames"]["1m"][0]["v"] = 2
            attach(result,requested,directory,"frozen engine","actual technical identity")
            later = result["markets"][0]["frames"]["1m"]["dataEvidence"]
            self.assertNotEqual(proof["inputSha256"],later["inputSha256"])
            self.assertEqual(path.read_bytes(),original_bytes)

    def test_noncandidate_gets_digest_but_never_fabricated_archive_or_execution(self):
        with tempfile.TemporaryDirectory() as root:
            result, requested = self.fixture()
            result["markets"][0]["frames"]["1m"].update(status="warming",candidate=None)
            directory = Path(root)/"inputs"
            self.assertEqual(attach(result,requested,directory,"engine","technical"),0)
            self.assertFalse(directory.exists())
            proof = result["markets"][0]["frames"]["1m"]["dataEvidence"]
            self.assertEqual(proof["nativeInputArchive"],"not_retained_non_candidate")
            self.assertFalse(proof["orderAuthority"])

    def test_corrupt_retained_evidence_is_rejected_instead_of_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            result, requested = self.fixture(); directory = Path(root)/"inputs"
            attach(result,requested,directory,"engine","technical")
            proof = result["markets"][0]["frames"]["1m"]["dataEvidence"]
            path = directory/(proof["inputSha256"]+".json.gz")
            path.write_bytes(gzip.compress(b"wrong inputs"))
            with self.assertRaisesRegex(ValueError,"does not match"):
                attach(result,requested,directory,"engine","technical")


if __name__ == "__main__":
    unittest.main()
