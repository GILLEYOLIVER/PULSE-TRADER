from __future__ import annotations

import unittest
from copy import deepcopy
from dataclasses import asdict

from trading_assistant.v2.error_review import review_closed_trades,development_priorities
from trading_assistant.v2.models import ExecutionSettings
from trading_assistant.v2.research import candidate_bank,development_result
from trading_assistant.v2.strategy import Strategy


class ErrorReviewCase(unittest.TestCase):
    def trades(self):
        return [{'id':str(i),'gross':3. if i<80 else -9.,'fees':1.,'net':2. if i<80 else -10.,
            'exit_reason':'TARGET' if i<80 else 'STOP','regime':'trend','side':'BUY',
            'entry':100.,'stop':91.,'exit':103. if i<80 else 91.,'tick':1.} for i in range(100)]

    def test_high_accuracy_can_lose_and_review_keeps_costs_and_all_losses(self):
        trades=self.trades();before=deepcopy(trades);row=review_closed_trades(trades,risk_budget=10.)
        self.assertEqual(trades,before);self.assertEqual(row['win_rate'],.8)
        self.assertEqual(row['gross_after_spread_slippage'],60.);self.assertEqual(row['commissions'],100.)
        self.assertEqual(row['net'],-40.);self.assertEqual(row['mean_winner_net'],2.)
        self.assertEqual(row['mean_nonpositive_loss'],10.)
        self.assertAlmostEqual(row['observed_net_break_even_win_rate'],10/12)
        self.assertIn('COMMISSIONS_ERASE_GROSS_EDGE',row['findings'])
        self.assertEqual(row['development_hypotheses'],['REWARD_COST_BALANCE'])
        self.assertEqual(row['exits'],{'TARGET':80,'STOP':20})

    def test_stop_gaps_and_forced_exits_preserved_without_calling_every_loss_a_gap(self):
        trades=self.trades();trades[-1].update(gross=-15.,fees=1.,net=-16.,exit=85.)
        trades[-2]['exit_reason']='FLATTEN'
        row=review_closed_trades(trades,costs=ExecutionSettings(fee_per_unit=0,spread_ticks=0,slippage_ticks=0),risk_budget=10.)
        self.assertEqual(row['adverse_stop_gap_ids'],['99']);self.assertEqual(row['losses_above_initial_budget'],1)
        self.assertEqual(row['exits']['FLATTEN'],1);self.assertEqual(row['nonpositive'],20)

    def test_small_empty_or_invalid_samples_do_not_invent_an_actionable_success(self):
        empty=review_closed_trades([]);self.assertIsNone(empty['win_rate'])
        self.assertIsNone(empty['observed_net_break_even_win_rate'])
        self.assertEqual(empty['development_hypotheses'],[])
        small=review_closed_trades(self.trades()[-10:]);self.assertEqual(small['development_hypotheses'],[])
        bad=self.trades();bad[0]['net']=20.
        with self.assertRaisesRegex(ValueError,'cash does not reconcile'):review_closed_trades(bad)
        with self.assertRaisesRegex(ValueError,'Repeated closed trade'):review_closed_trades([self.trades()[0]]*100)

    def test_development_feedback_keeps_original_financial_gate_and_external_data_out(self):
        review=review_closed_trades(self.trades())
        metrics={'trades':100,'win_rate':.8,'net':-40.,'fees':100.,'max_drawdown':200.,'expectancy':-.4}
        reports=[{'passed':True,'metrics':metrics,'outcome_review':review}]*3
        row=development_result(asdict(Strategy()),reports)
        self.assertFalse(row['eligible']);self.assertEqual(row['aggregate']['net'],-120.)
        self.assertEqual(row['error_review']['phase'],'DEVELOPMENT_ONLY')
        self.assertEqual(development_priorities(reports),['REWARD_COST_BALANCE'])
        # An external report is not an input to this development-only function or bank.
        self.assertEqual(development_priorities([{'external_outcome_review':review}]),[])

    def test_next_bank_declares_fixed_experiments_within_original_size_and_preserves_reference(self):
        reference=asdict(Strategy(reward_r=.5,stop_atr=2.5))
        old=candidate_bank(3,reference,36)
        new=candidate_bank(3,reference,36,development_priorities=['REWARD_COST_BALANCE','ENTRY_SELECTIVITY'])
        self.assertEqual(len(new),36);self.assertEqual(new[0],reference)
        self.assertEqual(new[2]['reward_r'],1.25);self.assertEqual(new[3]['reward_r'],2.)
        self.assertTrue(new[4]['require_trend_slope']);self.assertEqual(new[4]['min_efficiency'],.2)
        self.assertEqual(old,candidate_bank(3,reference,36,development_priorities=[]))
        self.assertEqual(new,candidate_bank(3,reference,36,development_priorities=['REWARD_COST_BALANCE','ENTRY_SELECTIVITY']))
        with self.assertRaises(ValueError):candidate_bank(3,reference,36,development_priorities=['UNKNOWN'])


if __name__=='__main__':unittest.main()
