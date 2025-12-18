from __future__ import annotations

import threading
import time
from collections import deque
from queue import Queue, Empty
from threading import Event
from typing import Deque, Dict, Optional

try:
    import customtkinter as ctk
except Exception:
    ctk = None  # type: ignore

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from trading_assistant.config import TradingAssistantConfig
from trading_assistant.app import run_market_pipeline


class TradingDashboard:
    def __init__(self) -> None:
        if ctk is None:
            raise RuntimeError("customtkinter não instalado. Instale: pip install customtkinter")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("PULSE-TRADER")
        self.root.geometry("1250x780")

        self.config = TradingAssistantConfig()

        self._stop_event = Event()
        self._runner_thread: threading.Thread | None = None
        self._events: Queue = Queue()
        self._commands: Queue = Queue()

        self._selected_symbol = tk.StringVar(value=(self.config.market_feed.symbols[0] if self.config.market_feed.symbols else "WIN"))
        self._mode = tk.StringVar(value="paper")

        self._candles: Dict[str, Deque[dict]] = {}
        self._max_candles = 120
        self._orderbook: Dict[str, dict] = {}
        self._last_signal: Dict[str, dict] = {}
        self._news_impact: Dict[str, float] = {}

        self._k_status = tk.StringVar(value="parado")
        self._k_price = tk.StringVar(value="—")
        self._k_reco = tk.StringVar(value="ESPERAR")
        self._k_conf = tk.StringVar(value="—")
        self._k_trades = tk.StringVar(value="0")
        self._k_newsimpact = tk.StringVar(value="0.00")

        self._qty_var = tk.StringVar(value="1")
        self._use_risk_var = tk.BooleanVar(value=True)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_events()

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self.root)
        top.pack(fill="x", padx=12, pady=12)

        self.btn_start = ctk.CTkButton(top, text="Iniciar", command=self.start, width=110)
        self.btn_start.pack(side="left", padx=6)

        self.btn_stop = ctk.CTkButton(top, text="Parar", command=self.stop, width=110, state="disabled")
        self.btn_stop.pack(side="left", padx=6)

        ctk.CTkLabel(top, text="Ativo:").pack(side="left", padx=(16, 6))
        self.symbol_menu = ctk.CTkOptionMenu(
            top,
            values=self.config.market_feed.symbols,
            variable=self._selected_symbol,
            command=lambda _: self._refresh_all(),
            width=140,
        )
        self.symbol_menu.pack(side="left", padx=6)

        ctk.CTkLabel(top, text="Modo:").pack(side="left", padx=(16, 6))
        self.mode_menu = ctk.CTkOptionMenu(top, values=["paper", "live"], variable=self._mode, width=110)
        self.mode_menu.pack(side="left", padx=6)

        self.lbl_status = ctk.CTkLabel(top, textvariable=self._k_status)
        self.lbl_status.pack(side="right", padx=10)

        main = ctk.CTkFrame(self.root)
        main.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=2)
        main.grid_rowconfigure(1, weight=1)

        # LEFT TOP (Chart + KPIs)
        left_top = ctk.CTkFrame(main)
        left_top.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        left_top.grid_rowconfigure(1, weight=1)
        left_top.grid_columnconfigure(0, weight=1)

        kpis = ctk.CTkFrame(left_top)
        kpis.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        for i in range(6):
            kpis.grid_columnconfigure(i, weight=1)

        self._kpi_box(kpis, "Preço", self._k_price).grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        self._kpi_box(kpis, "Recomendação", self._k_reco).grid(row=0, column=1, sticky="ew", padx=6, pady=6)
        self._kpi_box(kpis, "Conf", self._k_conf).grid(row=0, column=2, sticky="ew", padx=6, pady=6)
        self._kpi_box(kpis, "NewsImpact", self._k_newsimpact).grid(row=0, column=3, sticky="ew", padx=6, pady=6)
        self._kpi_box(kpis, "Trades", self._k_trades).grid(row=0, column=4, sticky="ew", padx=6, pady=6)

        chart_area = ctk.CTkFrame(left_top)
        chart_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.fig = Figure(figsize=(8, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Candles (mock)")
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_area)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

        # RIGHT TOP (Book + Order panel)
        right_top = ctk.CTkFrame(main)
        right_top.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))
        right_top.grid_rowconfigure(0, weight=1)
        right_top.grid_rowconfigure(1, weight=0)
        right_top.grid_columnconfigure(0, weight=1)

        book_frame = ctk.CTkFrame(right_top)
        book_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        book_frame.grid_rowconfigure(0, weight=1)
        book_frame.grid_columnconfigure(0, weight=1)

        self.book = ttk.Treeview(book_frame, columns=("ask_qty", "price", "bid_qty"), show="headings", height=18)
        self.book.heading("ask_qty", text="Ask Qtd")
        self.book.heading("price", text="Preço")
        self.book.heading("bid_qty", text="Bid Qtd")
        self.book.column("ask_qty", width=90, anchor="e")
        self.book.column("price", width=90, anchor="center")
        self.book.column("bid_qty", width=90, anchor="w")
        self.book.pack(fill="both", expand=True)

        order_frame = ctk.CTkFrame(right_top)
        order_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        order_frame.grid_columnconfigure(0, weight=1)
        order_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(order_frame, text="Ordem Manual", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 6)
        )

        ctk.CTkLabel(order_frame, text="Qtd:").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        self.qty_entry = ctk.CTkEntry(order_frame, textvariable=self._qty_var)
        self.qty_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=4)

        self.chk_risk = ctk.CTkCheckBox(order_frame, text="Usar sizing por risco", variable=self._use_risk_var)
        self.chk_risk.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 10))

        self.btn_buy = ctk.CTkButton(order_frame, text="COMPRAR (BUY)", command=lambda: self._send_order("BUY"))
        self.btn_buy.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

        self.btn_sell = ctk.CTkButton(order_frame, text="VENDER (SELL)", command=lambda: self._send_order("SELL"))
        self.btn_sell.grid(row=3, column=1, sticky="ew", padx=10, pady=(0, 10))

        # LEFT BOTTOM (Signals/Exec)
        left_bottom = ctk.CTkFrame(main)
        left_bottom.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(8, 0))
        left_bottom.grid_rowconfigure(0, weight=1)
        left_bottom.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(left_bottom, columns=("ts", "symbol", "type", "side", "conf", "price", "status"), show="headings")
        for col, txt, w in [
            ("ts", "Hora", 90),
            ("symbol", "Ativo", 70),
            ("type", "Tipo", 80),
            ("side", "Lado", 70),
            ("conf", "Conf", 70),
            ("price", "Preço", 90),
            ("status", "Status", 90),
        ]:
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

        # RIGHT BOTTOM (News/Logs)
        right_bottom = ctk.CTkFrame(main)
        right_bottom.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(8, 0))
        right_bottom.grid_rowconfigure(0, weight=1)
        right_bottom.grid_columnconfigure(0, weight=1)

        tabs = ctk.CTkTabview(right_bottom)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        tab_news = tabs.add("Notícias")
        tab_logs = tabs.add("Logs")

        self.txt_news = ctk.CTkTextbox(tab_news)
        self.txt_news.pack(fill="both", expand=True, padx=10, pady=10)

        self.txt_logs = ctk.CTkTextbox(tab_logs)
        self.txt_logs.pack(fill="both", expand=True, padx=10, pady=10)

        self._log("PULSE-TRADER pronto (mock market + news real via APIs).")

    def _kpi_box(self, parent, title: str, var: tk.StringVar):
        box = ctk.CTkFrame(parent)
        ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 0))
        ctk.CTkLabel(box, textvariable=var, font=ctk.CTkFont(size=16)).pack(anchor="w", padx=10, pady=(4, 8))
        return box

    def _set_running_ui(self, running: bool) -> None:
        self._k_status.set("rodando" if running else "parado")
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")

    def _log(self, msg: str) -> None:
        self.txt_logs.insert("end", f"{time.strftime('%H:%M:%S')} | {msg}\n")
        self.txt_logs.see("end")

    def _news(self, msg: str) -> None:
        self.txt_news.insert("end", f"{time.strftime('%H:%M:%S')} | {msg}\n")
        self.txt_news.see("end")

    # Pipeline
    def start(self) -> None:
        if self._runner_thread and self._runner_thread.is_alive():
            self._log("Já está rodando.")
            return

        self.config.execution.mode = self._mode.get().strip().lower()

        self._stop_event.clear()
        self._set_running_ui(True)
        self._log(f"Iniciando pipeline... modo={self.config.execution.mode}")

        def _run():
            import asyncio
            try:
                asyncio.run(run_market_pipeline(
                    self.config,
                    runtime_seconds=10**9,
                    stop_event=self._stop_event,
                    event_queue=self._events,
                    command_queue=self._commands,
                ))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Erro no pipeline: {e}"))
            finally:
                self.root.after(0, lambda: self._set_running_ui(False))
                self.root.after(0, lambda: self._log("Pipeline finalizado."))

        self._runner_thread = threading.Thread(target=_run, daemon=True)
        self._runner_thread.start()

    def stop(self) -> None:
        if not (self._runner_thread and self._runner_thread.is_alive()):
            self._log("Não está rodando.")
            self._set_running_ui(False)
            return
        self._log("Parando pipeline agora...")
        self._k_status.set("parando...")
        self._stop_event.set()

    def _on_close(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
        self.root.after(200, self.root.destroy)

    # Orders (dupla confirmação)
    def _send_order(self, side: str) -> None:
        symbol = self._selected_symbol.get()
        if not (self._runner_thread and self._runner_thread.is_alive()):
            messagebox.showwarning("PULSE-TRADER", "Inicie o pipeline antes de enviar ordens.")
            return

        price = self._get_last_price(symbol)
        if price is None:
            messagebox.showwarning("PULSE-TRADER", "Sem preço ainda para este ativo.")
            return

        qty = self._compute_qty(symbol, float(price))
        if qty <= 0:
            messagebox.showwarning("PULSE-TRADER", "Quantidade inválida.")
            return

        sl, tp, conf = self._derive_sl_tp_conf(symbol, float(price), side)
        mode = self._mode.get().strip().lower()

        if not messagebox.askyesno(
            f"CONFIRMAÇÃO 1/2 — {mode.upper()} — {side} {symbol}",
            f"Ativo: {symbol}\nLado: {side}\nQtd: {qty:.2f}\nPreço: {price:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}\n\nConfirma?"
        ):
            return

        text = simpledialog.askstring("CONFIRMAÇÃO 2/2", "Digite CONFIRMAR para enviar:", parent=self.root)
        if (text or "").strip().upper() != "CONFIRMAR":
            self._log("Ordem cancelada (confirmação 2/2).")
            return

        self._commands.put({
            "type": "ORDER",
            "symbol": symbol,
            "side": side,
            "qty": float(qty),
            "sl": float(sl),
            "tp": float(tp),
            "confidence": float(conf),
            "reason": "manual_ui",
        })
        self._log(f"Ordem enviada: {side} {symbol} qty={qty:.2f} (modo={mode})")

    def _get_last_price(self, symbol: str) -> Optional[float]:
        dq = self._candles.get(symbol)
        if not dq:
            return None
        return float(dq[-1].get("close", 0.0))

    def _compute_qty(self, symbol: str, price: float) -> float:
        if self._use_risk_var.get():
            sig = self._last_signal.get(symbol)
            atr = float(sig.get("meta", {}).get("atr", max(price * 0.002, 1.0))) if sig else max(price * 0.002, 1.0)
            stop_dist = max(atr * 1.0, price * 0.001)
            risk_money = float(self.config.risk.capital) * float(self.config.risk.risk_per_trade)
            qty = risk_money / stop_dist
            return max(1.0, qty)
        try:
            return float(self._qty_var.get().replace(",", "."))
        except Exception:
            return 0.0

    def _derive_sl_tp_conf(self, symbol: str, price: float, side: str):
        sig = self._last_signal.get(symbol)
        if sig:
            sl = float(sig.get("sl", price))
            tp = float(sig.get("tp", price))
            conf = float(sig.get("confidence", 0.6))
            if str(sig.get("side", "")).upper() != side.upper():
                sl = price + abs(price - sl) if side.upper() == "SELL" else price - abs(price - sl)
                tp = price - abs(tp - price) if side.upper() == "SELL" else price + abs(tp - price)
            return sl, tp, conf
        dist = max(price * 0.003, 1.0)
        return (price - dist, price + dist * 1.5, 0.55) if side.upper() == "BUY" else (price + dist, price - dist * 1.5, 0.55)

    # Events
    def _poll_events(self) -> None:
        processed = 0
        while processed < 300:
            try:
                ev = self._events.get_nowait()
            except Empty:
                break

            processed += 1
            et = ev.get("type")
            payload = ev.get("payload", {})

            if et == "status":
                self._set_running_ui(bool(payload.get("running", False)))

            elif et == "candle":
                sym = payload.get("symbol", "")
                if not sym:
                    continue
                dq = self._candles.setdefault(sym, deque(maxlen=self._max_candles))
                dq.append(payload)
                if sym == self._selected_symbol.get():
                    self._k_price.set(f"{float(payload.get('close', 0.0)):.2f}")
                    self._refresh_chart()

            elif et == "orderbook":
                sym = payload.get("symbol", "")
                book = payload.get("book", None)
                if sym and book:
                    self._orderbook[sym] = book
                    if sym == self._selected_symbol.get():
                        self._refresh_book()

            elif et == "news":
                title = str(payload.get("title", ""))
                src = str(payload.get("source", ""))
                sent = float(payload.get("sentiment", 0.0))
                imp = float(payload.get("impact", 0.0))
                self._news(f"[{src}] ({sent:+.2f} | imp {imp:.2f}) {title[:140]}")

            elif et == "news_impact":
                sym = str(payload.get("symbol", ""))
                sc = float(payload.get("score", 0.0))
                self._news_impact[sym] = sc
                if sym == self._selected_symbol.get():
                    self._k_newsimpact.set(f"{sc:.2f}")

            elif et == "signal":
                sym = str(payload.get("symbol", ""))
                if sym:
                    self._last_signal[sym] = payload
                    if sym == self._selected_symbol.get():
                        side = str(payload.get("side", "WAIT")).upper()
                        conf = float(payload.get("confidence", 0.0))
                        self._k_reco.set("COMPRAR" if side == "BUY" else "VENDER" if side == "SELL" else "ESPERAR")
                        self._k_conf.set(f"{conf:.2f}")
                    ts = str(payload.get("ts", ""))[-8:] or time.strftime("%H:%M:%S")
                    self.tree.insert("", "end", values=(ts, sym, "SIGNAL", str(payload.get("side","")).upper(), f"{float(payload.get('confidence',0.0)):.2f}", f"{float(payload.get('price',0.0)):.2f}", "OK"))
                    self.tree.yview_moveto(1)

            elif et == "execution":
                sym = str(payload.get("symbol", ""))
                ts = str(payload.get("ts", ""))[-8:] or time.strftime("%H:%M:%S")
                side = str(payload.get("side", "")).upper()
                price = float(payload.get("filled_price", 0.0))
                status = str(payload.get("status", ""))
                self.tree.insert("", "end", values=(ts, sym, "EXEC", side, "—", f"{price:.2f}", status))
                self.tree.yview_moveto(1)
                try:
                    cur = int(self._k_trades.get())
                except Exception:
                    cur = 0
                self._k_trades.set(str(cur + 1))

            elif et == "log":
                self._log(str(payload.get("msg", "")))

        self.root.after(120, self._poll_events)

    def _refresh_all(self) -> None:
        sym = self._selected_symbol.get()
        self._k_newsimpact.set(f"{float(self._news_impact.get(sym, 0.0)):.2f}")
        self._refresh_chart()
        self._refresh_book()

    def _refresh_chart(self) -> None:
        sym = self._selected_symbol.get()
        dq = self._candles.get(sym)

        self.ax.clear()
        self.ax.set_title(f"Candles (mock) — {sym}")
        self.ax.set_xlabel("tempo")
        self.ax.set_ylabel("preço")

        if not dq or len(dq) < 2:
            self.ax.text(0.5, 0.5, "Sem dados ainda", transform=self.ax.transAxes, ha="center", va="center")
            self.canvas.draw_idle()
            return

        data = list(dq)[-80:]
        import matplotlib.patches as mpatches
        for i, c in enumerate(data):
            o = float(c.get("open", 0))
            h = float(c.get("high", 0))
            l = float(c.get("low", 0))
            cl = float(c.get("close", 0))
            self.ax.plot([i, i], [l, h], linewidth=1)
            y0 = min(o, cl)
            height = abs(cl - o) if abs(cl - o) > 1e-9 else 0.0001
            self.ax.add_patch(mpatches.Rectangle((i - 0.35, y0), 0.7, height))

        self.ax.set_xlim(-1, len(data) + 1)
        self.canvas.draw_idle()

    def _refresh_book(self) -> None:
        sym = self._selected_symbol.get()
        book = self._orderbook.get(sym)
        for it in self.book.get_children():
            self.book.delete(it)

        if not book:
            self.book.insert("", "end", values=("—", "Sem book", "—"))
            return

        asks = book.get("asks", [])
        bids = book.get("bids", [])
        levels = min(len(asks), len(bids), 12)
        for i in range(levels):
            a = asks[i]
            b = bids[i]
            self.book.insert("", "end", values=(f"{a['qty']:.0f}", f"{(a['price']):.2f}", f"{b['qty']:.0f}"))

    def run(self) -> None:
        self.root.mainloop()


def launch_dashboard() -> None:
    TradingDashboard().run()
