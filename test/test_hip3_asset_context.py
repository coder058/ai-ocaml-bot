"""Synthetic index/provenance cases, not actual liquidity or trading results."""
import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
from hip3_asset_context import parse,collect

# SOURCE: artificial native decimal fields and timestamps test protocol checks.
NOW=datetime(2026,10,5,tzinfo=timezone.utc)
META={"universe":[{"name":"xyz:EUR"},{"name":"xyz:DXY","isDelisted":True}]}
ROW={"openInterest":"21934476.8000000007","funding":"-0.000014207",
     "dayNtlVlm":"50.00","dayBaseVlm":"40.00","markPx":"1.12","oraclePx":"1.11",
     "privateExtra":"NOT_FOR_EXPORT"}


class AssetContextTests(unittest.TestCase):
    def test_native_decimal_provenance_is_current_only_and_delisted_is_not_available(self):
        meta,rows=parse([META,[ROW,ROW]],NOW)
        self.assertIs(meta,META)
        self.assertEqual(set(rows),{"xyz:EUR"})
        row=rows["xyz:EUR"]
        self.assertEqual(row["openInterestRaw"],ROW["openInterest"])
        self.assertEqual(row["fundingRateRaw"],ROW["funding"])
        self.assertFalse(row["historicalSeries"]);self.assertFalse(row["orderAuthority"])
        self.assertIsNone(row["providerTimestamp"]);self.assertIsNone(row["winProbability"])
        self.assertNotIn("privateExtra",row)

    def test_bad_scope_order_duplicates_or_naive_receipt_fail_closed(self):
        for payload in ([META,[ROW]], [{"universe":[{"name":"BTC"}]},[ROW]],
                        [{"universe":[{"name":"xyz:EUR"},{"name":"xyz:EUR"}]},[ROW,ROW]]):
            with self.assertRaises(ValueError):parse(payload,NOW)
        with self.assertRaises(ValueError):parse([META,[ROW,ROW]],NOW.replace(tzinfo=None))

    def test_missing_or_invalid_metrics_do_not_fabricate_values_or_invalidate_other_fields(self):
        for key,value in (("openInterest","nan"),("openInterest","-1"),("markPx","0"),
                          ("dayNtlVlm",True),("oraclePx",None),("funding","Infinity")):
            with self.subTest(key=key,value=value):
                _,rows=parse([META,[{**ROW,key:value},ROW]],NOW)
                self.assertEqual(rows["xyz:EUR"]["status"],"partial")
                self.assertIn(key,rows["xyz:EUR"]["missing"])
        _,rows=parse([META,[{**ROW,"openInterest":"0","funding":"0"},ROW]],NOW)
        self.assertEqual(rows["xyz:EUR"]["status"],"descriptive")

    def test_success_is_one_public_request_without_credentials_or_wallet(self):
        request=Mock(return_value=[META,[ROW,ROW]])
        _,contexts,errors=collect(request,lambda:NOW)
        self.assertEqual(errors,[]);self.assertEqual(len(contexts),1)
        request.assert_called_once_with("https://api.hyperliquid.xyz/info",body={"type":"metaAndAssetCtxs","dex":"xyz"})

    def test_new_context_failure_uses_old_catalog_but_no_fresh_metric_is_invented(self):
        for bad in (TimeoutError(),[META,[]]):
            request=Mock(side_effect=[bad,META])
            meta,contexts,errors=collect(request,lambda:NOW)
            self.assertIs(meta,META);self.assertEqual(contexts,{})
            self.assertEqual(len(errors),1)
            self.assertEqual(request.call_args.kwargs["body"],{"type":"meta","dex":"xyz"})


if __name__=="__main__":unittest.main()
