"""Synthetic provider fixtures; no account connection or performance claims."""
import sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
import oanda_practice as o

class PracticeTests(unittest.TestCase):
    def test_http_requests_reuse_practice_tls_and_do_not_allow_post(self):
        from unittest.mock import MagicMock
        conn=MagicMock();conn.getresponse.return_value.status=200
        conn.getresponse.return_value.read.return_value=b'{"prices": []}'
        with patch('oanda_practice._connection',None),patch('oanda_practice.http.client.HTTPSConnection',return_value=conn) as factory:
            o.get('/v3/accounts/001-123/pricing','SYNTHETIC')
            o.get('/v3/accounts/001-123/summary','SYNTHETIC')
            self.assertEqual(factory.call_count,1)
            self.assertEqual(factory.call_args.args[0],'api-fxpractice.oanda.com')
            self.assertTrue(all(call.args[0]=='GET' for call in conn.request.call_args_list))
    def test_missing_credential_is_explicit_not_connected(self):
        with tempfile.TemporaryDirectory() as d:
            r=o.connect(Path(d)/'status.json',Path(d)/'missing.env')
            self.assertFalse(r['connected']);self.assertEqual(r['reason'],'practice_credentials_missing')
    def test_production_cannot_be_selected_and_token_not_exported(self):
        self.assertEqual(o.ORIGIN,'https://api-fxpractice.oanda.com')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'private.env';p.write_text('OANDA_PRACTICE_TOKEN=SYNTHETIC_SECRET\nOANDA_PRACTICE_ACCOUNT=001-123\n');p.chmod(0o600)
            replies=[{'account':{}},{'instruments':[{'name':'EUR_USD','type':'CURRENCY'},
                {'name':'WTICO_USD','type':'CFD'}]},{'prices':[{'instrument':'EUR_USD','status':'non-tradeable'}]}]
            with patch('oanda_practice.get',side_effect=replies):r=o.connect(Path(d)/'status.json',p)
            self.assertTrue(r['connected']);self.assertEqual(r['catalogCount'],1)
            self.assertNotIn('SYNTHETIC_SECRET',str(r));self.assertFalse(r['orderAuthority'])
    def test_open_or_unfinished_candles_are_excluded(self):
        # SOURCE: synthetic OHLC fixture verifies provider closed-candle semantics.
        candle={'time':'2026-10-01T12:00:00Z','complete':True,'mid':{'o':'1','h':'2','l':'0.5','c':'1'},'volume':1}
        now=datetime(2026,10,1,12,1,tzinfo=timezone.utc)
        self.assertEqual(len(o.closed_candles({'frame':'1m','candles':[candle]},now)),1)
        self.assertEqual(o.closed_candles({'frame':'1m','candles':[{**candle,'complete':False}]},now),[])
        self.assertEqual(o.closed_candles({'frame':'5m','candles':[candle]},now),[])

if __name__=='__main__':unittest.main()
