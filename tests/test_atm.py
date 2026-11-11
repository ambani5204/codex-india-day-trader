import csv
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from india_trader.live_forward import select_atm_contract

class ATMSelectionTests(unittest.TestCase):
    def test_uses_new_expiry_and_atm_and_correct_right(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'instruments.csv'
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['exchange','name','instrument_type','expiry','strike','lot_size','tradingsymbol'])
                w.writeheader()
                for expiry in ['2026-11-05','2026-11-12','2026-11-19']:
                    for strike in [25800,25850,25900]:
                        for side in ['CE','PE']:
                            w.writerow({'exchange':'NFO','name':'NIFTY','instrument_type':side,
                                        'expiry':expiry,'strike':strike,'lot_size':65,
                                        'tradingsymbol':f'NIFTY{expiry}{strike}{side}'})
                w.writerow({'exchange':'BFO','name':'SENSEX','instrument_type':'PE','expiry':'2026-11-12',
                            'strike':85000,'lot_size':20,'tradingsymbol':'SENSEXTESTPE'})
            sym,inst=select_atm_contract(p,'NSE:NIFTY 50','BUY',25846,dt.date(2026,11,11))
            self.assertIn('2026-11-12',sym);self.assertIn('25850CE',sym)
            self.assertEqual(inst['lot_size'],'65')
            sym,_=select_atm_contract(p,'NSE:NIFTY 50','SELL',25846,dt.date(2026,11,11))
            self.assertIn('25850PE',sym)
            sym,_=select_atm_contract(p,'BSE:SENSEX','SELL',85100,dt.date(2026,11,11))
            self.assertEqual(sym,'BFO:SENSEXTESTPE')

if __name__=='__main__':unittest.main()
