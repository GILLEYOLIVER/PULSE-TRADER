from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from trading_assistant.config import SignalEngineConfig
from trading_assistant.validation.performance import PerformanceTracker, PerformanceSnapshot


@dataclass
class CalibratorReport:
    reason: str
    old_threshold: float
    new_threshold: float
    old_stop_atr_mult: float
    new_stop_atr_mult: float
    old_reward_r: float
    new_reward_r: float
    snapshot: PerformanceSnapshot


class OnlineCalibrator:
    """Calibração online simples e explicável.

    Objetivo: melhorar consistência em stops curtos + alvos longos sem overfit.
    Ajustes leves:
    - threshold: seletividade dos sinais
    - stop_atr_mult: largura do stop (curto mas não suicida)
    - reward_r: alvo em R (mantém longo, mas evita impossível)

    Regras (heurísticas):
    - Se drawdown em R estiver alto e win_rate baixo -> aumenta seletividade e/ou stop um pouco.
    - Se win_rate alto e avg_r bom -> pode reduzir seletividade (mais oportunidades) com cuidado.
    """

    def __init__(
        self,
        cfg: SignalEngineConfig,
        every_trades: int = 10,
        step_threshold: float = 0.10,
        step_stop: float = 0.05,
        step_rr: float = 0.10,
        threshold_min: float = 1.2,
        threshold_max: float = 4.5,
        stop_min: float = 0.35,
        stop_max: float = 1.50,
        rr_min: float = 1.5,
        rr_max: float = 5.0,
    ) -> None:
        self.cfg = cfg
        self.every_trades = int(max(5, every_trades))
        self.step_threshold = float(step_threshold)
        self.step_stop = float(step_stop)
        self.step_rr = float(step_rr)

        self.threshold_min = float(threshold_min)
        self.threshold_max = float(threshold_max)
        self.stop_min = float(stop_min)
        self.stop_max = float(stop_max)
        self.rr_min = float(rr_min)
        self.rr_max = float(rr_max)

        self._last_calibrated_trades = 0

    def maybe_calibrate(self, tracker: PerformanceTracker) -> Optional[CalibratorReport]:
        snap = tracker.snapshot()
        trades = int(snap.trades)

        if trades < self.every_trades:
            return None

        if trades - self._last_calibrated_trades < self.every_trades:
            return None

        self._last_calibrated_trades = trades

        old_thr = float(self.cfg.threshold)
        old_stop = float(getattr(self.cfg, "stop_atr_mult", 0.70))
        old_rr = float(getattr(self.cfg, "reward_r", 3.00))

        thr = old_thr
        stop = old_stop
        rr = old_rr

        reason_parts = []

        # Heurísticas baseadas em performance
        if snap.win_rate < 0.38 and snap.max_dd_r > 4.0:
            thr += self.step_threshold
            stop += self.step_stop
            rr = max(self.rr_min, rr - self.step_rr)  # reduz levemente alvo se estiver impossível
            reason_parts.append("baixo win_rate + drawdown alto -> mais seletivo + stop um pouco maior")

        elif snap.win_rate < 0.40:
            stop += self.step_stop
            reason_parts.append("win_rate baixo -> stop um pouco maior")

        elif snap.win_rate > 0.55 and snap.avg_r > 0.15:
            # está bom: pode pegar um pouco mais de oportunidades
            thr -= self.step_threshold
            reason_parts.append("win_rate bom + avgR bom -> um pouco menos seletivo")

        # Se profit factor muito baixo, aumenta seletividade
        if snap.profit_factor < 0.9 and trades >= self.every_trades:
            thr += self.step_threshold
            reason_parts.append("profit factor baixo -> mais seletivo")

        # clamp
        thr = min(self.threshold_max, max(self.threshold_min, thr))
        stop = min(self.stop_max, max(self.stop_min, stop))
        rr = min(self.rr_max, max(self.rr_min, rr))

        # aplica
        self.cfg.threshold = float(thr)
        self.cfg.stop_atr_mult = float(stop)
        self.cfg.reward_r = float(rr)

        reason = "; ".join(reason_parts) if reason_parts else "ajuste periódico (leve)"

        return CalibratorReport(
            reason=reason,
            old_threshold=old_thr,
            new_threshold=float(thr),
            old_stop_atr_mult=old_stop,
            new_stop_atr_mult=float(stop),
            old_reward_r=old_rr,
            new_reward_r=float(rr),
            snapshot=snap,
        )
