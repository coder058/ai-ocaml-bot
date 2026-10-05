"""Actual native executable verification, synthetic inputs, no broker calls."""
import copy
import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path
import native_input_fixture
from verify_decision_input import verify


@unittest.skipUnless(native_input_fixture.ENGINE.exists() and os.name == 'posix',
                     'requires the real Linux OCaml analyzer')
class ProofTests(unittest.TestCase):
    def fixture(self, directory):
        root=Path(directory)
        result=native_input_fixture.document(root,'QQQ','Alpaca equities','4h')
        request={'asOf':result['asOf'],'venue':'Alpaca equities','symbol':'QQQ','frame':'4h',
                 'reading':result['markets'][0]['frames']['4h']}
        return root,request

    def test_actual_native_replay_accepts_only_original_input_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root,request=self.fixture(directory)
            proof=verify(request,root)
            self.assertTrue(proof['verified'])
            self.assertFalse(proof['orderAuthority'])
            self.assertEqual(proof['inputSha256'],request['reading']['dataEvidence']['inputSha256'])
            self.assertEqual(proof['analysisAsOf'],request['asOf'])

    def test_missing_proof_archive_wrong_scope_clock_and_changed_readings_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root,original=self.fixture(directory)
            modifiers=[lambda r:r['reading'].pop('dataEvidence'),
                lambda r:r.update(venue='Hyperliquid HIP-3'),
                lambda r:r.update(symbol='SPY'),
                lambda r:r.update(frame='1h'),
                lambda r:r.update(asOf='2099-01-01T00:00:00Z'),
                lambda r:r['reading'].update(close=101),
                lambda r:r['reading'].update(invalidationLevel=98),
                lambda r:r['reading'].update(candleShapes=['invented_pattern']),
                lambda r:r['reading']['dataEvidence'].update(nativeInputArchive='not_retained_non_candidate'),
                lambda r:r['reading']['dataEvidence'].update(inputSha256='../private')]
            for modify in modifiers:
                request=copy.deepcopy(original);modify(request)
                with self.subTest(request=request), self.assertRaises(ValueError):
                    verify(request,root)
            evidence=original['reading']['dataEvidence']
            (root/'decision-inputs'/(evidence['inputSha256']+'.json.gz')).unlink()
            with self.assertRaises(FileNotFoundError):verify(original,root)

    def test_corrupt_native_archive_and_replaced_executable_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root,request=self.fixture(directory);evidence=request['reading']['dataEvidence']
            archive=root/'decision-inputs'/(evidence['inputSha256']+'.json.gz')
            original=archive.read_bytes()
            with gzip.open(archive,'wb') as file:file.write(b'changed input')
            with self.assertRaisesRegex(ValueError,'bytes'):verify(request,root)
            archive.write_bytes(original)
            engine=root/'frozen-analyzers'/(evidence['engineSha256']+'.exe')
            # SOURCE: this isolated test copy inherited dune's read-only mode.
            engine.chmod(0o700)
            engine.write_bytes(b'replaced executable')
            with self.assertRaisesRegex(ValueError,'executable'):verify(request,root)


if __name__=='__main__':unittest.main()
