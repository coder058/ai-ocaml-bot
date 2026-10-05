"""Synthetic received-event cases; no real prices, fills or performance claims."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from archived_quote_reference import augment, latest_from_tail, receipt_text
from decision_quote_capture import normalize_at, quote_time

# SOURCE: artificial quote prices/sizes/timestamps test exact receipt ordering.
NOW = datetime(2026,10,5,0,0,1,tzinfo=timezone.utc)
NS = 1791158400 * 1_000_000_000
QUOTE = {"T":"q", "S":"BTC/USD", "t":"2026-10-05T00:00:00.123456789Z",
         "bp":100,"ap":101,"bs":1,"as":1}
SCOPE = {"Alpaca crypto":["BTC/USD"],"Alpaca equities":["QQQ"]}


def record(event=QUOTE, receipt=NS+200_000_000):
    return {"feed":"alpaca-us", "event":event, "receivedAtNs":receipt}


def write(root, records, day="2026-10-05", folder="us", trailing=b""):
    path=root/folder/f"{day}.jsonl"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(b"".join(json.dumps(r).encode()+b"\n" for r in records)+trailing)
    return path


class ArchivedQuoteTests(unittest.TestCase):
    def test_nanoseconds_and_latest_worse_quote_are_preserved_without_price_selection(self):
        self.assertEqual(receipt_text(NS+200_000_001),"2026-10-05T00:00:00.200000001Z")
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            newer={**QUOTE,"ap":103,"t":"2026-10-05T00:00:00.300000001Z"}
            path=write(root,[record(),record(newer,NS+400_000_001)])
            quotes,diag=latest_from_tail(path,"Alpaca crypto",["BTC/USD"],quote_time("2026-10-05T00:00:01Z"))
            self.assertEqual(quotes["BTC/USD"]["ask"],103)
            self.assertEqual(quotes["BTC/USD"]["receivedAt"],"2026-10-05T00:00:00.400000001Z")
            self.assertEqual(diag["bytesRead"],path.stat().st_size)

    def test_tail_is_bounded_and_partial_or_unfinished_lines_are_not_consumed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=write(Path(directory),[record(),record(receipt=NS+400_000_000)],trailing=json.dumps(record(receipt=NS+900_000_000)).encode())
            quotes,diag=latest_from_tail(path,"Alpaca crypto",["BTC/USD"],quote_time("2026-10-05T00:00:01Z"),limit=500)
            self.assertLessEqual(diag["bytesRead"],500)
            self.assertEqual(quotes["BTC/USD"]["receivedAt"],"2026-10-05T00:00:00.400000000Z")

    def test_future_receipts_and_wrong_symbols_feeds_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path=write(Path(directory),[record(),record(receipt=NS+2_000_000_000),
                record({**QUOTE,"S":"DOGE/USD"}),{**record(),"feed":"other"}])
            values,_=latest_from_tail(path,"Alpaca crypto",["BTC/USD"],quote_time("2026-10-05T00:00:01Z"))
            self.assertEqual(set(values),{"BTC/USD"})
            self.assertEqual(values["BTC/USD"]["receivedAt"],"2026-10-05T00:00:00.200000000Z")

    def test_invalid_latest_and_ambiguous_same_receipt_never_fall_back_to_older_price(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for rows in ([record(),record({**QUOTE,"bs":0},NS+400_000_000)],
                         [record(),record({**QUOTE,"ap":102})]):
                path=write(root,rows)
                values,_=latest_from_tail(path,"Alpaca crypto",["BTC/USD"],quote_time("2026-10-05T00:00:01Z"))
                self.assertEqual(values["BTC/USD"]["status"],"invalid")

    def test_selection_keeps_rest_if_newer_and_never_mutates_original_or_invents_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);write(root,[record()])
            old={"Alpaca crypto|BTC/USD":normalize_at(None,"2026-10-05T00:00:01Z","Alpaca crypto","BTC/USD")}
            selected,diag=augment(old,SCOPE,root,NOW)
            value=selected["Alpaca crypto|BTC/USD"]
            self.assertEqual(value["transport"],"existing_archived_websocket")
            self.assertEqual(old["Alpaca crypto|BTC/USD"]["status"],"missing")
            self.assertFalse(value["orderAuthority"]);self.assertIsNone(value["winProbability"])
            self.assertNotIn("fillPrice",value)
            self.assertEqual(diag["streamSelected"],1)
            newer=normalize_at({**QUOTE,"t":"2026-10-05T00:00:00.5Z"},"2026-10-05T00:00:00.6Z","Alpaca crypto","BTC/USD")
            result,_=augment({"Alpaca crypto|BTC/USD":newer},SCOPE,root,NOW)
            self.assertIs(result["Alpaca crypto|BTC/USD"],newer)

    def test_fresh_at_receipt_but_expired_at_read_is_not_backfilled(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            quote={**QUOTE,"t":"2026-10-04T23:59:55.999999999Z"}
            write(root,[record(quote,NS)],day="2026-10-04")
            value,_=augment({},SCOPE,root,NOW)
            self.assertEqual(value,{})
            edge={**QUOTE,"t":"2026-10-04T23:59:56Z"}
            write(root,[record(edge,NS)],day="2026-10-04")
            value,_=augment({},SCOPE,root,NOW)
            self.assertEqual(value["Alpaca crypto|BTC/USD"]["quoteAt"],edge["t"])

    def test_stock_capture_provenance_is_iex_and_unsupported_scopes_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            write(root,[record({**QUOTE,"S":"QQQ"})],folder="iex")
            values,_=augment({},SCOPE,root,NOW)
            self.assertEqual(values["Alpaca equities|QQQ"]["feed"],"iex")
            for venue,symbols in (("Alpaca equities",["AAPL"]),("Alpaca crypto",["DOGE/USD"]),("other",["QQQ"])):
                with self.assertRaises(ValueError):
                    latest_from_tail(root/"none",venue,symbols,quote_time("2026-10-05T00:00:01Z"))

    def test_absent_or_unreadable_capture_does_not_destroy_actual_rest_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            rest={"Alpaca crypto|BTC/USD":normalize_at(QUOTE,"2026-10-05T00:00:00.2Z","Alpaca crypto","BTC/USD")}
            with patch.object(Path,"open",side_effect=PermissionError):
                result,diag=augment(rest,SCOPE,root,NOW)
                self.assertEqual(result,rest)
                self.assertTrue(all(d["status"]=="archive_read_error" for d in diag["archives"]))
            result,diag=augment(rest,SCOPE,root,NOW)
            self.assertEqual(result,rest)
            self.assertTrue(all(d["status"]=="archive_absent" for d in diag["archives"]))


if __name__=="__main__":unittest.main()
