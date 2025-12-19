from __future__ import annotations
import queue
from datetime import datetime
import customtkinter as ctk

from trader_tool.app.engine import EngineStatus
from trader_tool.risk.risk_manager import RiskState

class PulseUI(ctk.CTk):
    def __init__(self, *, on_start, on_stop):
        super().__init__()
        self.title("PULSE TRADER — Dashboard")
        self.geometry("980x540")
        ctk.set_appearance_mode("dark")

        self.on_start = on_start
        self.on_stop = on_stop
        self._ui_queue: queue.Queue = queue.Queue()

        self.top = ctk.CTkFrame(self)
        self.top.pack(fill="x", padx=12, pady=(12, 6))

        self.lbl_status = ctk.CTkLabel(self.top, text="Status: PARADO", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_status.pack(side="left", padx=10, pady=8)

        self.btn_start = ctk.CTkButton(self.top, text="Iniciar (Paper)", command=self._start)
        self.btn_start.pack(side="right", padx=6)
        self.btn_stop = ctk.CTkButton(self.top, text="Pausar (Kill Switch)", fg_color="#9b1c1c", command=self._stop)
        self.btn_stop.pack(side="right", padx=6)

        self.body = ctk.CTkFrame(self)
        self.body.pack(fill="both", expand=True, padx=12, pady=6)

        self.left = ctk.CTkFrame(self.body)
        self.left.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=10)

        self.right = ctk.CTkFrame(self.body)
        self.right.pack(side="right", fill="both", expand=True, padx=(6, 0), pady=10)

        self.card_now = ctk.CTkFrame(self.left)
        self.card_now.pack(fill="x", padx=10, pady=10)

        self.lbl_action = ctk.CTkLabel(self.card_now, text="AÇÃO AGORA: —", font=ctk.CTkFont(size=22, weight="bold"))
        self.lbl_action.pack(anchor="w", padx=12, pady=(12, 4))

        self.lbl_plan = ctk.CTkLabel(self.card_now, text="Plano: —", justify="left")
        self.lbl_plan.pack(anchor="w", padx=12, pady=(0, 6))

        self.lbl_diag = ctk.CTkLabel(self.card_now, text="Diagnóstico: —", justify="left")
        self.lbl_diag.pack(anchor="w", padx=12, pady=(0, 12))

        self.card_market = ctk.CTkFrame(self.left)
        self.card_market.pack(fill="x", padx=10, pady=(0, 10))

        self.lbl_market = ctk.CTkLabel(self.card_market, text="Mercado: —", justify="left")
        self.lbl_market.pack(anchor="w", padx=12, pady=12)

        self.card_risk = ctk.CTkFrame(self.right)
        self.card_risk.pack(fill="x", padx=10, pady=10)

        self.lbl_risk = ctk.CTkLabel(self.card_risk, text="Risco: —", justify="left")
        self.lbl_risk.pack(anchor="w", padx=12, pady=12)

        self.card_log = ctk.CTkFrame(self.right)
        self.card_log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.txt = ctk.CTkTextbox(self.card_log, wrap="word")
        self.txt.pack(fill="both", expand=True, padx=10, pady=10)
        self.txt.insert("end", "Log do UI iniciado.\n")
        self.txt.configure(state="disabled")

        self.after(150, self._poll)

    def push_status(self, st: EngineStatus, rs: RiskState):
        self._ui_queue.put((st, rs))

    def _start(self):
        self.on_start()

    def _stop(self):
        self.on_stop()

    def _log(self, line: str):
        self.txt.configure(state="normal")
        self.txt.insert("end", f"{datetime.now().strftime('%H:%M:%S')} | {line}\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                st, rs = self._ui_queue.get_nowait()
                self.lbl_status.configure(text=f"Status: {'RODANDO' if st.running else 'PARADO'} | Modo: {st.mode}")

                if st.last_tick:
                    t = st.last_tick
                    self.lbl_market.configure(text=f"Mercado\nAtivo: {t.symbol}\nPreço: {t.price:.2f}\nHorário: {t.ts}")

                if st.last_signal:
                    s = st.last_signal
                    self.lbl_action.configure(text=f"AÇÃO AGORA: {s.side.value} ({s.confidence:.2f})")

                    if st.last_trade:
                        a = st.last_trade
                        plan = (f"Entrada ref: {a.entry_hint:.2f}\n"
                                f"Stop: {a.stop_price:.2f}\n"
                                f"Alvo: {a.target_price:.2f}\n"
                                f"Contratos: {a.contracts}\n"
                                f"Motivo: {a.rationale}")
                    else:
                        plan = f"Motivo: {s.rationale}"

                    self.lbl_plan.configure(text=f"Plano:\n{plan}")
                    self.lbl_diag.configure(text=f"Diagnóstico:\n{st.diagnostics or '—'}")
                    self._log(f"Sinal: {s.side.value} {s.symbol} conf={s.confidence:.2f}")

                cooldown = rs.cooldown_until.isoformat() if rs.cooldown_until else "—"
                self.lbl_risk.configure(text=f"Risco\nPnL Hoje: {rs.pnl_today:.2f}\nStops seguidos: {rs.stops_in_row}\nCooldown até: {cooldown}")

        except queue.Empty:
            pass

        self.after(150, self._poll)
