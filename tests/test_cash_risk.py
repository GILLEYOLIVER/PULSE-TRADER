from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import timedelta

from trading_assistant.v2.models import Limits,ExecutionSettings,Instrument,Decision,Bar
from trading_assistant.v2.execution import PaperEngine
from trading_assistant.v2.ledger import SimulationLedger
from test_v2 import START


class CashRiskCase(unittest.TestCase):
    budget=130.5696

    def engine(self,side='SELL',costs=None,quote=100.1):
        limits=replace(Limits(),capital=100000.,risk_fraction=self.budget/100000.,daily_loss=1000.,
            weekly_loss=3000.,monthly_loss=10000.,daily_target=2000.,max_contracts=100000,max_exposure=100000.)
        costs=costs or ExecutionSettings(spread_ticks=0,slippage_ticks=1,fee_per_unit=0,fee_bps=10)
        ledger=SimulationLedger();self.addCleanup(ledger.close)
        spec=Instrument('WDO',1.,.1,margin=1.)
        engine=PaperEngine(ledger,limits,costs,{'WDO':spec})
        engine.on_bar(self.bar(0,quote),automatic=False)
        now=START+timedelta(minutes=1);direction=1 if side=='BUY' else -1
        stop=101. if side=='SELL' else 99.
        d=Decision('WDO',side,quote,stop,quote+direction*3,now,now+timedelta(minutes=3),'trend','numeric stress')
        return engine,ledger,d,spec

    def bar(self,index,price,*,high=None,low=None):
        return Bar('WDO',START+timedelta(minutes=index),price,price if high is None else high,
            price if low is None else low,price,10000.,'SYNTHETIC',60)

    def test_reported_short_stop_breach_is_fixed_through_actual_fill_and_exit(self):
        engine,ledger,d,spec=self.engine()
        d=replace(d,target=97.)
        order=engine.submit(d,requested=100);self.assertEqual(order['qty'],100)
        engine.on_bar(self.bar(1,99.9,high=100.,low=99.5),automatic=False)
        position=next(iter(ledger.read()['positions'].values()))
        self.assertEqual(position['qty'],86)
        engine.on_bar(self.bar(2,100.5,high=101.5,low=100.),automatic=False)
        trade=ledger.read()['trades'][0]
        self.assertEqual(trade['exit_reason'],'STOP');self.assertAlmostEqual(trade['exit'],101.1)
        self.assertAlmostEqual(-trade['net'],129.0774)
        self.assertLessEqual(-trade['net'],self.budget+1e-8)
        self.assertAlmostEqual(trade['fees'],trade['entry_fee']+engine.costs.fee(trade['exit'],1.,86))

    def test_reservation_includes_rounded_adverse_entry_and_actual_stop_fee(self):
        costs=ExecutionSettings(spread_ticks=.5,slippage_ticks=1,fee_per_unit=.2,fee_bps=10)
        engine,ledger,d,spec=self.engine('BUY',costs,quote=100.02)
        order=engine.submit(d);entry=costs.entry_price(d.price,d.side,spec.tick)
        exit_price=costs.exit_price(d.stop,d.side,spec.tick)
        self.assertAlmostEqual(entry,100.2)
        expected=order['qty']*((entry-exit_price)*spec.point_value+costs.fee(entry,1)+costs.fee(exit_price,1))
        self.assertAlmostEqual(order['reserved_risk'],expected)
        self.assertLessEqual(order['reserved_risk'],self.budget+1e-8)
        self.assertAlmostEqual(order['reserved_exposure'],entry*order['qty'])
        self.assertEqual(ledger.read()['orders'][order['id']]['reserved_risk'],order['reserved_risk'])

    def test_explicit_filled_entry_equal_to_signal_does_not_charge_entry_slippage_again(self):
        engine,ledger,d,spec=self.engine()
        qty,reason=engine.risk.assess(ledger.read(),d,spec,d.ts,entry=d.price)
        stop_exit=101.1
        risk=(stop_exit-d.price)+engine.costs.fee(d.price,1)+engine.costs.fee(stop_exit,1)
        self.assertEqual(reason,'Approved');self.assertEqual(qty,int(self.budget/risk))

    def test_period_worst_matches_stop_cash_and_uses_mark_when_already_beyond_stop(self):
        engine,ledger,d,spec=self.engine();engine.submit(d)
        engine.on_bar(self.bar(1,99.9),automatic=False)
        state=ledger.read();position=next(iter(state['positions'].values()))
        for mark in (99.9,102.):
            state['marks']['WDO']=mark
            _,unrealized,worst=engine.risk.period_pnl(state,START+timedelta(minutes=2))
            exit_quote=max(mark,position['stop'])+.1
            expected=(position['entry']-exit_quote)*position['qty']-position['entry_fee']-engine.costs.fee(exit_quote,1,position['qty'])
            self.assertAlmostEqual(unrealized-worst,expected)

    def test_legacy_pending_reservations_are_refreshed_without_changing_requested_quantity(self):
        engine,ledger,d,spec=self.engine();order=engine.submit(d,requested=100)
        state=ledger.read();state['orders'][order['id']]['reserved_risk']=0.
        state['orders'][order['id']].pop('reserved_exposure')
        restarted=PaperEngine(ledger,engine.limits,engine.costs,engine.specs,engine.strategy)
        saved=ledger.read()['orders'][order['id']]
        self.assertEqual(saved['qty'],100);self.assertGreater(saved['reserved_risk'],0.)
        self.assertGreater(saved['reserved_exposure'],0.)

    def test_invalid_adverse_prices_reject_before_creating_exposure(self):
        engine,ledger,d,spec=self.engine('BUY')
        order=engine.submit(replace(d,stop=.05))
        self.assertEqual(order['qty'],0);self.assertEqual(ledger.read()['positions'],{})
        self.assertIn('invalid',order['message'])
        with self.assertRaises(ValueError):engine.costs.entry_price(.05,'SELL',.1)

    def test_gap_past_stop_keeps_the_full_loss_instead_of_clipping_to_budget(self):
        engine,ledger,d,spec=self.engine();engine.submit(d)
        engine.on_bar(self.bar(1,99.9),automatic=False)
        engine.on_bar(self.bar(2,110.,high=111.,low=109.),automatic=False)
        trade=ledger.read()['trades'][0]
        self.assertGreater(-trade['net'],self.budget)
        self.assertAlmostEqual(trade['exit'],110.1)


if __name__=='__main__':unittest.main()
