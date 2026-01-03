from __future__ import annotations

import threading
import time
from collections import deque
from queue import Queue, Empty
from threading import Event
from typing import Deque, Dict, Optional, List

try:
    import customtkinter as ctk
except Exception:
    ctk = None  # type: ignore

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, simpledialog

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from trading_assistant.config import TradingAssistantConfig
from trading_assistant.app import run_market_pipeline


# =========================
# Tooltip
# =========================
class ToolTip:
    """Tooltip simples (passar o mouse e aparece uma dica)."""

    def __init__(self, widget, text: str, delay_ms: int = 450):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id = None
        self._tip = None

        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = None

    def _show(self):
        if self._tip or not self.text:
            return

        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10

        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except Exception:
            pass
        tip.geometry(f"+{x}+{y}")

        bg = "#0B0F14"
        fg = "#E5E7EB"
        lbl = tk.Label(
            tip,
            text=self.text,
            justify="left",
            background=bg,
            foreground=fg,
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
            font=("Arial", 11),
        )
        lbl.pack()
        self._tip = tip

    def _hide(self, _event=None):
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
        self._tip = None


# =========================
# Dashboard
# =========================
class TradingDashboard:
    def __init__(self) -> None:
        if ctk is None:
            raise RuntimeError("customtkinter não instalado. Instale: pip install customtkinter")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("PULSE-TRADER")

        # Abre em tela cheia (windowed) ocupando o monitor inteiro
        self._apply_fullscreen_geometry()

        self.config = TradingAssistantConfig()

        self._stop_event = Event()
        self._runner_thread: threading.Thread | None = None
        self._events: Queue = Queue()
        self._commands: Queue = Queue()

        self._selected_symbol = tk.StringVar(
            value=(self.config.market_feed.symbols[0] if self.config.market_feed.symbols else "WIN")
        )
        self._mode = tk.StringVar(value="Simulação")

        # Timeframe (tempo por vela)
        self._tf_var = tk.StringVar(value=f"{self.config.market_feed.timeframe_seconds}s")

        # Descrição amigável dos ativos (para pessoas comuns)
        self._asset_desc = {
            "WIN": "Mini Índice (B3)",
            "WDO": "Mini Dólar (B3)",
            "DOL": "Dólar Cheio (B3)",
            "IND": "Índice Cheio (B3)",
            "BTC": "Bitcoin (Criptomoeda)",
            "ETH": "Ethereum (Criptomoeda)",
        }
        self._asset_desc_var = tk.StringVar(value=self._asset_desc.get(self._selected_symbol.get(), ""))

        # Cache de mercado / sinal / notícias
        self._candles: Dict[str, Deque[dict]] = {}
        self._max_candles = 500
        self._orderbook: Dict[str, dict] = {}
        self._last_signal: Dict[str, dict] = {}
        self._news_impact: Dict[str, float] = {}

        # Shadow position (para desenhar linhas no gráfico)
        self._shadow_pos: Dict[str, dict] = {}

        # Notícias
        self._news_items: Deque[dict] = deque(maxlen=300)
        self._news_filter_var = tk.StringVar(value="Tudo")  # default: tudo
        self._news_lang_filter_var = tk.StringVar(value="Todos")

        # Visualização do gráfico
        self._view_bars_var = tk.IntVar(value=80)
        self._view_offset_var = tk.IntVar(value=0)
        self._follow_live_var = tk.BooleanVar(value=True)
        self._view_bars_label = tk.StringVar(value=str(self._view_bars_var.get()))

        # Escala vertical (Auto x Fixa tipo Profit)
        self._y_mode_var = tk.StringVar(value="Fixa (Profit)")
        self._y_fixed_points_var = tk.IntVar(value=200)  # faixa total de preço/pontos
        self._y_fixed_points_label = tk.StringVar(value=str(self._y_fixed_points_var.get()))

        # KPIs
        self._k_status = tk.StringVar(value="parado")
        self._k_price = tk.StringVar(value="—")
        self._k_reco = tk.StringVar(value="ESPERAR")
        self._k_conf = tk.StringVar(value="—")
        self._k_trades = tk.StringVar(value="0")
        self._k_newsimpact = tk.StringVar(value="0.00")
        self._k_winrate = tk.StringVar(value="—")
        self._k_avg_r = tk.StringVar(value="—")

        # Ordem manual
        self._qty_var = tk.StringVar(value="1")
        self._use_risk_var = tk.BooleanVar(value=True)

        # Livro (labels)
        self._book_rows: List[dict] = []
        self._spread_var = tk.StringVar(value="Spread: —")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_events()

    # -------------------------
    # Janela em tela cheia
    # -------------------------
    def _apply_fullscreen_geometry(self) -> None:
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        # um pequeno respiro para barra do sistema em alguns ambientes
        self.root.geometry(f"{sw}x{sh}+0+0")
        try:
            self.root.minsize(1100, 720)
        except Exception:
            pass

        # Atalho: ESC sai de fullscreen windowed (volta tamanho padrão)
        self.root.bind("<Escape>", lambda _e: self._apply_default_geometry())
        self.root.bind("<F11>", lambda _e: self._apply_fullscreen_geometry())

    def _apply_default_geometry(self) -> None:
        self.root.geometry("1250x780")
        try:
            self.root.minsize(1100, 720)
        except Exception:
            pass

    # -------------------------
    # UI
    # -------------------------
    def _build_ui(self) -> None:
        bg = "#0B0F14"
        panel = "#0F172A"
        border = "#243041"

        self.root.configure(fg_color=bg)

        # Topbar
        top = ctk.CTkFrame(self.root, fg_color=panel, corner_radius=14, border_width=1, border_color=border)
        top.pack(fill="x", padx=14, pady=14)

        self.btn_start = ctk.CTkButton(top, text="Iniciar", command=self.start, width=110)
        self.btn_start.pack(side="left", padx=8, pady=10)

        self.btn_stop = ctk.CTkButton(top, text="Parar", command=self.stop, width=110, state="disabled")
        self.btn_stop.pack(side="left", padx=8, pady=10)

        ctk.CTkLabel(top, text="Ativo:").pack(side="left", padx=(16, 6))

        self.symbol_menu = ctk.CTkOptionMenu(
            top,
            values=self.config.market_feed.symbols,
            variable=self._selected_symbol,
            command=lambda _v: self._on_symbol_changed(),
            width=140,
        )
        self.symbol_menu.pack(side="left", padx=6)

        self.lbl_asset_desc = ctk.CTkLabel(top, textvariable=self._asset_desc_var, text_color="#9CA3AF")
        self.lbl_asset_desc.pack(side="left", padx=(8, 14))

        ctk.CTkLabel(top, text="Tempo da vela:").pack(side="left", padx=(0, 6))

        self.tf_menu = ctk.CTkOptionMenu(
            top,
            values=["1s", "5s", "10s", "15s", "30s", "60s"],
            variable=self._tf_var,
            command=self._on_timeframe_change,
            width=90,
        )
        self.tf_menu.pack(side="left", padx=6)

        ctk.CTkLabel(top, text="Modo:").pack(side="left", padx=(16, 6))

        self.mode_menu = ctk.CTkOptionMenu(top, values=["Simulação", "Real"], variable=self._mode, width=120)
        self.mode_menu.pack(side="left", padx=6)

        # Botão Ajuda
        self.btn_help = ctk.CTkButton(top, text="?", width=36, command=self._open_help)
        self.btn_help.pack(side="right", padx=(6, 12), pady=10)

        self.lbl_status = ctk.CTkLabel(top, textvariable=self._k_status, text_color="#E5E7EB")
        self.lbl_status.pack(side="right", padx=12, pady=10)

        # Corpo principal
        main = ctk.CTkFrame(self.root, fg_color=bg)
        main.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        # 70/30 (gráfico vs coluna direita)
        main.grid_columnconfigure(0, weight=7)
        main.grid_columnconfigure(1, weight=3)
        main.grid_rowconfigure(0, weight=3)
        main.grid_rowconfigure(1, weight=1)

        # ===== ESQUERDA =====
        left_top = ctk.CTkFrame(main, fg_color=panel, corner_radius=14, border_width=1, border_color=border)
        left_top.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        left_top.grid_rowconfigure(1, weight=1)
        left_top.grid_columnconfigure(0, weight=1)

        kpis = ctk.CTkFrame(left_top, fg_color=panel)
        kpis.grid(row=0, column=0, sticky="ew", padx=12, pady=12)

        for i in range(7):
            kpis.grid_columnconfigure(i, weight=1)

        self._kpi_box(kpis, "Preço", self._k_price).grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        self._kpi_box(kpis, "Ação agora", self._k_reco).grid(row=0, column=1, sticky="ew", padx=6, pady=6)
        self._kpi_box(kpis, "Confiança", self._k_conf).grid(row=0, column=2, sticky="ew", padx=6, pady=6)
        self._kpi_box(kpis, "Impacto notícias", self._k_newsimpact).grid(row=0, column=3, sticky="ew", padx=6, pady=6)
        self._kpi_box(kpis, "Operações", self._k_trades).grid(row=0, column=4, sticky="ew", padx=6, pady=6)
        self._kpi_box(kpis, "Win rate", self._k_winrate).grid(row=0, column=5, sticky="ew", padx=6, pady=6)
        self._kpi_box(kpis, "Avg R", self._k_avg_r).grid(row=0, column=6, sticky="ew", padx=6, pady=6)

        chart_area = ctk.CTkFrame(left_top, fg_color=bg, border_width=1, border_color=border, corner_radius=14)
        chart_area.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        # Controles do gráfico
        ctrl = ctk.CTkFrame(chart_area, fg_color=panel, corner_radius=12)
        ctrl.pack(side="top", fill="x", padx=10, pady=(10, 0))

        ctk.CTkLabel(ctrl, text="Velas na tela:", text_color="#E5E7EB").pack(side="left", padx=(10, 6), pady=6)

        self.btn_zoom_in = ctk.CTkButton(ctrl, text="+", width=40, command=self._zoom_in)
        self.btn_zoom_in.pack(side="left", padx=2, pady=6)

        self.btn_zoom_out = ctk.CTkButton(ctrl, text="-", width=40, command=self._zoom_out)
        self.btn_zoom_out.pack(side="left", padx=2, pady=6)

        self.slider_window = ctk.CTkSlider(
            ctrl,
            from_=20,
            to=self._max_candles,
            number_of_steps=max(1, self._max_candles - 20),
            variable=self._view_bars_var,
            command=lambda v: self._on_window_changed(v),
        )
        self.slider_window.pack(side="left", fill="x", expand=True, padx=10, pady=6)

        self.lbl_window_val = ctk.CTkLabel(ctrl, textvariable=self._view_bars_label, width=50, text_color="#E5E7EB")
        self.lbl_window_val.pack(side="left", padx=(0, 10), pady=6)

        self.btn_left = ctk.CTkButton(ctrl, text="◀", width=30, command=self._pan_left)
        self.btn_left.pack(side="left", padx=(4, 2), pady=6)

        self.btn_live = ctk.CTkButton(ctrl, text="●", width=30, command=self._go_live)
        self.btn_live.pack(side="left", padx=2, pady=6)

        self.btn_right = ctk.CTkButton(ctrl, text="▶", width=30, command=self._pan_right)
        self.btn_right.pack(side="left", padx=(2, 10), pady=6)

        self.chk_follow = ctk.CTkCheckBox(
            ctrl,
            text="Seguir",
            variable=self._follow_live_var,
            command=self._on_follow_toggle
        )
        self.chk_follow.pack(side="left", padx=(0, 12), pady=6)

        # Escala Y
        ctk.CTkLabel(ctrl, text="Escala:", text_color="#E5E7EB").pack(side="left", padx=(8, 4), pady=6)

        self.y_menu = ctk.CTkOptionMenu(
            ctrl,
            values=["Auto", "Fixa (Profit)"],
            variable=self._y_mode_var,
            command=lambda _v: self._refresh_chart(),
            width=130,
        )
        self.y_menu.pack(side="left", padx=(2, 10), pady=6)

        ctk.CTkLabel(ctrl, text="Faixa:", text_color="#E5E7EB").pack(side="left", padx=(4, 4), pady=6)

        self.y_slider = ctk.CTkSlider(
            ctrl,
            from_=40,
            to=800,
            number_of_steps=760,
            variable=self._y_fixed_points_var,
            command=lambda v: self._on_y_range_changed(v),
        )
        self.y_slider.pack(side="left", fill="x", expand=False, padx=(0, 8), pady=6)

        self.lbl_y_val = ctk.CTkLabel(ctrl, textvariable=self._y_fixed_points_label, width=52, text_color="#E5E7EB")
        self.lbl_y_val.pack(side="left", padx=(0, 10), pady=6)

        # Canvas Matplotlib
        self.fig = Figure(figsize=(8, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_area)
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True, padx=10, pady=10)
        self._apply_chart_style()
        self._refresh_chart()

        # LEFT BOTTOM: tabela de sinais/execuções
        left_bottom = ctk.CTkFrame(main, fg_color=panel, corner_radius=14, border_width=1, border_color=border)
        left_bottom.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(10, 0))
        left_bottom.grid_rowconfigure(0, weight=1)
        left_bottom.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            left_bottom,
            columns=("ts", "symbol", "type", "side", "conf", "price", "status"),
            show="headings",
            height=8,
        )

        for col, txt, w in [
            ("ts", "Hora", 80),
            ("symbol", "Ativo", 70),
            ("type", "Tipo", 86),
            ("side", "Ação", 86),
            ("conf", "Confiança", 90),
            ("price", "Preço", 90),
            ("status", "Status", 90),
        ]:
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor="center")

        self.tree.pack(fill="both", expand=True, padx=12, pady=12)

        # Cores de linhas (COMPRA / VENDA / ESPERAR)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Treeview", background="#0B0F14", fieldbackground="#0B0F14", foreground="#E5E7EB")
        style.map("Treeview", background=[("selected", "#1F2937")], foreground=[("selected", "#E5E7EB")])

        self.tree.tag_configure("BUY", foreground="#22C55E")
        self.tree.tag_configure("SELL", foreground="#EF4444")
        self.tree.tag_configure("WAIT", foreground="#60A5FA")

        # ===== DIREITA (Livro + Ordens + Notícias) =====
        right_col = ctk.CTkFrame(main, fg_color=panel, corner_radius=14, border_width=1, border_color=border)
        right_col.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(10, 0))
        right_col.grid_rowconfigure(0, weight=2)
        right_col.grid_rowconfigure(1, weight=3)
        right_col.grid_columnconfigure(0, weight=1)

        right_top = ctk.CTkFrame(right_col, fg_color=panel)
        right_top.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        right_top.grid_rowconfigure(0, weight=3)
        right_top.grid_rowconfigure(1, weight=1)
        right_top.grid_columnconfigure(0, weight=1)

        # Livro
        book_frame = ctk.CTkFrame(right_top, fg_color=bg, corner_radius=12, border_width=1, border_color=border)
        book_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 10))
        book_frame.grid_rowconfigure(1, weight=1)
        book_frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(book_frame, fg_color=panel, corner_radius=10)
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        hdr.grid_columnconfigure(0, weight=1)
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text="Livro de Ofertas", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=6
        )

        self.lbl_spread = ctk.CTkLabel(hdr, textvariable=self._spread_var, font=ctk.CTkFont(size=11),
                                       text_color="#9CA3AF")
        self.lbl_spread.grid(row=0, column=1, sticky="e", padx=10, pady=6)

        self.book_table = ctk.CTkFrame(book_frame, fg_color=bg)
        self.book_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.book_table.grid_columnconfigure(0, weight=1)
        self.book_table.grid_columnconfigure(1, weight=1)
        self.book_table.grid_columnconfigure(2, weight=1)

        header_font = ctk.CTkFont(size=10, weight="bold")
        ctk.CTkLabel(self.book_table, text="Venda", font=header_font, text_color="#EF4444").grid(
            row=0, column=0, sticky="ew", padx=6, pady=(4, 2)
        )
        ctk.CTkLabel(self.book_table, text="Preço", font=header_font, text_color="#E5E7EB").grid(
            row=0, column=1, sticky="ew", padx=6, pady=(4, 2)
        )
        ctk.CTkLabel(self.book_table, text="Compra", font=header_font, text_color="#22C55E").grid(
            row=0, column=2, sticky="ew", padx=6, pady=(4, 2)
        )

        self._book_rows.clear()
        row_font = ctk.CTkFont(size=10)

        for i in range(8):  # 8 níveis (mais espaço para Ordem)
            r = i + 1
            sell = ctk.CTkLabel(self.book_table, text="—", font=row_font, text_color="#EF4444")
            price = ctk.CTkLabel(self.book_table, text="—", font=row_font, text_color="#E5E7EB")
            buy = ctk.CTkLabel(self.book_table, text="—", font=row_font, text_color="#22C55E")

            sell.grid(row=r, column=0, sticky="ew", padx=6, pady=1)
            price.grid(row=r, column=1, sticky="ew", padx=6, pady=1)
            buy.grid(row=r, column=2, sticky="ew", padx=6, pady=1)

            self._book_rows.append({"sell": sell, "price": price, "buy": buy})

        # Ordem
        order_frame = ctk.CTkFrame(right_top, fg_color=bg, corner_radius=12, border_width=1, border_color=border)
        order_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        order_frame.grid_columnconfigure(0, weight=1)
        order_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(order_frame, text="Ordem", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 6)
        )

        ctk.CTkLabel(order_frame, text="Qtd:").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.qty_entry = ctk.CTkEntry(order_frame, textvariable=self._qty_var, width=80)
        self.qty_entry.grid(row=1, column=1, sticky="e", padx=12, pady=4)

        self.chk_risk = ctk.CTkCheckBox(order_frame, text="Risco", variable=self._use_risk_var)
        self.chk_risk.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))

        self.btn_buy = ctk.CTkButton(
            order_frame,
            text="COMPRAR",
            command=lambda: self._send_order("BUY"),
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#16A34A",
        )
        self.btn_buy.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

        self.btn_sell = ctk.CTkButton(
            order_frame,
            text="VENDER",
            command=lambda: self._send_order("SELL"),
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#DC2626",
        )
        self.btn_sell.grid(row=3, column=1, sticky="ew", padx=10, pady=(0, 10))

        # Notícias / Logs
        right_bottom = ctk.CTkFrame(right_col, fg_color=panel)
        right_bottom.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        right_bottom.grid_rowconfigure(0, weight=1)
        right_bottom.grid_columnconfigure(0, weight=1)

        tabs = ctk.CTkTabview(right_bottom)
        tabs.pack(fill="both", expand=True, padx=0, pady=0)
        tab_news = tabs.add("Notícias")
        tab_logs = tabs.add("Logs")

        # Área de notícias - ajustada para usar as mesmas cores
        news_top = ctk.CTkFrame(tab_news, fg_color=bg, corner_radius=12)
        news_top.pack(fill="x", padx=8, pady=(8, 6))
        news_top.grid_columnconfigure(0, weight=1)
        news_top.grid_columnconfigure(1, weight=1)

        self.news_filter_menu = ctk.CTkOptionMenu(
            news_top,
            values=["Tudo", "Somente este ativo"],
            variable=self._news_filter_var,
            command=lambda _v: self._render_news(),
            width=160,
            font=ctk.CTkFont(size=11),
        )
        self.news_filter_menu.grid(row=0, column=0, sticky="w", padx=8, pady=8)

        self.news_lang_menu = ctk.CTkOptionMenu(
            news_top,
            values=["Todos", "PT", "EN", "ES"],
            variable=self._news_lang_filter_var,
            command=lambda _v: self._render_news(),
            width=90,
            font=ctk.CTkFont(size=11),
        )
        self.news_lang_menu.grid(row=0, column=1, sticky="e", padx=8, pady=8)

        self.txt_news = ctk.CTkTextbox(
            tab_news,
            font=ctk.CTkFont(size=11),
            fg_color=bg,
            border_color=border,
            border_width=1,
            corner_radius=12
        )
        self.txt_news.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.txt_logs = ctk.CTkTextbox(
            tab_logs,
            font=ctk.CTkFont(size=11),
            fg_color=bg,
            border_color=border,
            border_width=1,
            corner_radius=12
        )
        self.txt_logs.pack(fill="both", expand=True, padx=8, pady=8)

        # Tooltips
        try:
            ToolTip(self.symbol_menu, "Escolha o ativo (ex.: WIN Mini Índice, BTC Bitcoin). ")
            ToolTip(self.tf_menu, "Define quanto tempo vale cada vela do gráfico.")
            ToolTip(self.mode_menu, "Simulação = não envia ordem real. Real = envia para corretora.")
            ToolTip(self.btn_zoom_in, "Zoom +: mostra menos velas e deixa as velas mais largas.")
            ToolTip(self.btn_zoom_out, "Zoom -: mostra mais velas e deixa as velas mais finas.")
            ToolTip(self.btn_left, "Voltar no histórico (ver velas anteriores).")
            ToolTip(self.btn_right, "Avançar no histórico.")
            ToolTip(self.btn_live, "Voltar para o ao vivo.")
            ToolTip(self.chk_follow, "Seguir: quando ligado, o gráfico acompanha as últimas velas automaticamente.")
            ToolTip(self.y_menu, "Auto = escala ajusta sozinha. Fixa (Profit) = faixa fixa em pontos.")
            ToolTip(self.y_slider, "Faixa vertical (pontos/preço) usada quando a escala está em Fixa.")
            ToolTip(self.news_filter_menu, "Filtra notícias: tudo ou somente do ativo selecionado.")
            ToolTip(self.news_lang_menu, "Filtra notícias por idioma.")
            ToolTip(self.btn_buy, "Envia ordem de COMPRAR (no modo escolhido).")
            ToolTip(self.btn_sell, "Envia ordem de VENDER (no modo escolhido).")
        except Exception:
            pass

        self._log("PULSE-TRADER pronto (simulação). ")
        self._render_news()
    def _kpi_box(self, parent, title: str, var: tk.StringVar):
        box = ctk.CTkFrame(parent, fg_color="#0B1220", corner_radius=12, border_width=1, border_color="#1F2A3A")
        ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=12, weight="bold"), text_color="#9CA3AF").pack(
            anchor="w", padx=10, pady=(8, 0)
        )
        ctk.CTkLabel(box, textvariable=var, font=ctk.CTkFont(size=16), text_color="#E5E7EB").pack(
            anchor="w", padx=10, pady=(2, 8)
        )
        return box

    # =========================
    # Ajuda (para leigos)
    # =========================
    def _open_help(self) -> None:
        w = ctk.CTkToplevel(self.root)
        w.title("Ajuda — Como usar o PULSE-TRADER")
        w.geometry("760x560")
        try:
            w.transient(self.root)
            w.grab_set()
        except Exception:
            pass

        title = ctk.CTkLabel(w, text="Entendendo os indicadores e ferramentas", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(anchor="w", padx=16, pady=(16, 8))

        text = ctk.CTkTextbox(w)
        text.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        sym = self._selected_symbol.get()
        desc = self._asset_desc.get(sym, "")
        tf = int(getattr(self.config.market_feed, "timeframe_seconds", 0) or 0)

        help_msg = (
            f"Ativo selecionado: {sym} {('- ' + desc) if desc else ''}\n"
            f"Tempo da vela: {tf}s (cada vela representa {tf} segundos de movimento de preço)\n\n"
            "O que aparece no topo:\n"
            "• Preço: último preço conhecido do ativo.\n"
            "• Ação agora: recomendação do sistema (COMPRAR / VENDER / ESPERAR).\n"
            "• Confiança: força do sinal (0% a 100%). Quanto maior, mais consistente ficou o sinal.\n"
            "• Impacto notícias: quanto as notícias recentes podem estar mexendo com o mercado (0.00 a 1.00).\n"
            "• Win rate / Avg R: desempenho do motor no paper automático (shadow trading).\n\n"
            "Livro de ofertas (à direita):\n"
            "• Venda (vermelho): quantidade que o mercado quer VENDER naquele preço.\n"
            "• Compra (verde): quantidade que o mercado quer COMPRAR naquele preço.\n"
            "• Spread: diferença entre o melhor preço de compra e o melhor preço de venda.\n\n"
            "Notícias:\n"
            "• Fonte: de onde a notícia veio (ex.: GDELT, Finnhub, Alpha Vantage).\n"
            "• Sentimento: negativo (-), neutro (0), positivo (+).\n"
            "• Impacto: importância estimada (0 a 1).\n\n"
            "Simulação x Real:\n"
            "• Simulação: treina e testa sem mandar ordens para corretora.\n"
            "• Real: manda ordem real (quando você integrar ao Profit/Corretora).\n\n"
            "Exemplos práticos:\n"
            "• Se aparecer COMPRAR com Confiança 70%+ e Impacto notícias baixo, é um sinal mais 'limpo'.\n"
            "• Se Impacto notícias estiver alto, espere volatilidade e use menor quantidade.\n"
            "• Use Zoom + / Zoom - para deixar as velas mais largas ou mais finas.\n"
            "• Escala Fixa (Profit): evita o eixo ficar pulando e melhora leitura.\n"
        )
        text.insert("end", help_msg)
        text.configure(state="disabled")

        btn = ctk.CTkButton(w, text="Fechar", command=w.destroy, width=120)
        btn.pack(pady=(0, 16))

    # =========================
    # Handlers
    # =========================
    def _on_symbol_changed(self) -> None:
        sym = self._selected_symbol.get()
        self._asset_desc_var.set(self._asset_desc.get(sym, ""))
        self._refresh_all()
        self._render_news()

    def _on_timeframe_change(self, value: str) -> None:
        try:
            seconds = int(str(value).replace("s", "").strip())
        except Exception:
            seconds = int(getattr(self.config.market_feed, "timeframe_seconds", 5) or 5)

        self.config.market_feed.timeframe_seconds = seconds
        self._tf_var.set(f"{seconds}s")

        if self._runner_thread and self._runner_thread.is_alive():
            self._log("Timeframe alterado. Para aplicar no fluxo, pare e inicie novamente.")

        self._refresh_chart()

    def _on_y_range_changed(self, _value: float) -> None:
        try:
            self._y_fixed_points_var.set(int(float(self._y_fixed_points_var.get())))
        except Exception:
            pass
        v = int(self._y_fixed_points_var.get())
        v = max(40, min(800, v))
        self._y_fixed_points_var.set(v)
        self._y_fixed_points_label.set(str(v))
        self._refresh_chart()

    def _set_running_ui(self, running: bool) -> None:
        self._k_status.set("rodando" if running else "parado")
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")

    def _log(self, msg: str) -> None:
        try:
            self.txt_logs.insert("end", f"{time.strftime('%H:%M:%S')} | {msg}\n")
            self.txt_logs.see("end")
        except Exception:
            pass

    # =========================
    # Gráfico
    # =========================
    def _apply_chart_style(self) -> None:
        bg = "#0B0F14"
        fg = "#E5E7EB"
        grid = "#243041"

        try:
            self.fig.patch.set_facecolor(bg)
        except Exception:
            pass

        self.ax.set_facecolor(bg)
        self.ax.tick_params(axis="both", colors=fg, labelcolor=fg)
        self.ax.xaxis.label.set_color(fg)
        self.ax.yaxis.label.set_color(fg)
        self.ax.title.set_color(fg)

        for sp in self.ax.spines.values():
            sp.set_color(grid)

        # eixo de preços à direita
        self.ax.yaxis.tick_right()
        self.ax.yaxis.set_label_position("right")

        try:
            self.ax.spines["left"].set_visible(False)
        except Exception:
            pass

        self.ax.grid(True, color=grid, alpha=0.35, linewidth=0.8)
        self.ax.set_axisbelow(True)

    def _clamp_view(self) -> None:
        bars = int(self._view_bars_var.get() or 80)
        bars = max(20, min(self._max_candles, bars))
        self._view_bars_var.set(bars)
        self._view_bars_label.set(str(bars))

        off = int(self._view_offset_var.get() or 0)
        self._view_offset_var.set(max(0, off))

    def _on_window_changed(self, _value: float) -> None:
        try:
            self._view_bars_var.set(int(float(self._view_bars_var.get())))
        except Exception:
            pass
        self._clamp_view()
        self._refresh_chart()

    def _zoom_in(self) -> None:
        self._clamp_view()
        bars = int(self._view_bars_var.get())
        new_bars = max(20, int(bars * 0.80))
        self._view_bars_var.set(new_bars)
        self._view_bars_label.set(str(new_bars))
        self._refresh_chart()

    def _zoom_out(self) -> None:
        self._clamp_view()
        bars = int(self._view_bars_var.get())
        new_bars = min(self._max_candles, int(bars * 1.25) + 1)
        self._view_bars_var.set(new_bars)
        self._view_bars_label.set(str(new_bars))
        self._refresh_chart()

    def _pan_left(self) -> None:
        self._clamp_view()
        bars = int(self._view_bars_var.get())
        step = max(5, bars // 4)
        self._follow_live_var.set(False)
        self._view_offset_var.set(int(self._view_offset_var.get()) + step)
        self._refresh_chart()

    def _pan_right(self) -> None:
        self._clamp_view()
        bars = int(self._view_bars_var.get())
        step = max(5, bars // 4)
        new_off = max(0, int(self._view_offset_var.get()) - step)
        self._view_offset_var.set(new_off)
        if new_off == 0 and self._follow_live_var.get():
            self._follow_live_var.set(True)
        self._refresh_chart()

    def _go_live(self) -> None:
        self._view_offset_var.set(0)
        self._follow_live_var.set(True)
        self._refresh_chart()

    def _on_follow_toggle(self) -> None:
        if self._follow_live_var.get():
            self._go_live()
        else:
            self._refresh_chart()

    def _refresh_chart(self) -> None:
        """Gráfico de velas com janela fixa + escala Auto/Fixa (Profit) e sem cortar o eixo da direita."""
        sym = self._selected_symbol.get()
        dq = self._candles.get(sym)

        self.ax.clear()
        self._apply_chart_style()

        # >>> IMPORTANTE: dá mais "respiro" para os números da direita não cortarem
        # (pad dos ticks + margens do subplot)
        try:
            self.ax.tick_params(axis="y", pad=10)  # afasta os números do eixo
        except Exception:
            pass

        tf = int(getattr(self.config.market_feed, "timeframe_seconds", 0) or 0)
        desc = self._asset_desc.get(sym, "")
        extra = f" — {desc}" if desc else ""
        self.ax.set_title(f"Gráfico de Preço (Velas){extra} — {sym} — {tf}s por vela")
        self.ax.set_xlabel("tempo")
        self.ax.set_ylabel("preço")

        self.ax.yaxis.tick_right()
        self.ax.yaxis.set_label_position("right")

        self._clamp_view()
        bars = int(self._view_bars_var.get())
        off = int(self._view_offset_var.get())

        if not dq or len(dq) < 2:
            self.ax.set_xlim(0, 1)
            self.ax.set_ylim(0, 1)
            self.ax.set_xticks([])
            self.ax.set_yticks([])
            for sp in self.ax.spines.values():
                sp.set_visible(False)

            self.ax.text(
                0.5, 0.52, "Sem dados ainda",
                transform=self.ax.transAxes,
                ha="center", va="center",
                color="#E5E7EB", fontsize=14,
            )
            self.ax.text(
                0.5, 0.42, "Clique em Iniciar para carregar o fluxo (simulação/mock).",
                transform=self.ax.transAxes,
                ha="center", va="center",
                color="#94A3B8", fontsize=11,
            )

            # >>> right menor = MAIS espaço para os números da direita
            self.fig.subplots_adjust(left=0.012, right=0.960, top=0.92, bottom=0.10)
            self.canvas.draw_idle()
            return

        all_data = list(dq)

        max_off = max(0, len(all_data) - 2)
        if off > max_off:
            off = max_off
            self._view_offset_var.set(off)

        end = max(0, len(all_data) - off)
        start = max(0, end - bars)
        view = all_data[start:end]

        pad_left = max(0, bars - len(view))

        wick_color = "#94A3B8"
        up_color = "#22C55E"
        down_color = "#EF4444"
        body_w = 0.70

        import matplotlib.patches as mpatches

        lows, highs = [], []

        for i, c in enumerate(view):
            x = pad_left + i

            o = float(c.get("open", 0))
            h = float(c.get("high", 0))
            l = float(c.get("low", 0))
            cl = float(c.get("close", 0))

            lows.append(l)
            highs.append(h)

            is_up = cl >= o
            body_color = up_color if is_up else down_color

            self.ax.plot([x, x], [l, h], linewidth=1.0, color=wick_color, alpha=0.9)

            y0 = min(o, cl)
            height = abs(cl - o)
            if height < 1e-9:
                height = 0.0001

            self.ax.add_patch(
                mpatches.Rectangle(
                    (x - body_w / 2, y0),
                    body_w,
                    height,
                    facecolor=body_color,
                    edgecolor=body_color,
                )
            )

        # respiro mínimo horizontal
        self.ax.set_xlim(-0.60, bars - 0.40)

        # ========= ESCALA Y =========
        y_mode = "Auto"
        try:
            y_mode = str(self._y_mode_var.get()).strip()
        except Exception:
            y_mode = "Auto"

        last_close = float(view[-1].get("close", 0.0)) if view else 0.0

        if (y_mode.lower().startswith("fixa") or "profit" in y_mode.lower()):
            try:
                rng = float(self._y_fixed_points_var.get())
            except Exception:
                rng = 200.0

            rng = max(40.0, min(2000.0, rng))
            half = rng / 2.0
            center = last_close if last_close != 0 else (sum(lows) / len(lows))

            # respiro mínimo vertical
            extra = max(rng * 0.01, 0.02)
            self.ax.set_ylim(center - half - extra, center + half + extra)
        else:
            lo = min(lows) if lows else (last_close - 1.0)
            hi = max(highs) if highs else (last_close + 1.0)
            pad = max((hi - lo) * 0.08, (abs(hi) * 0.002) + 0.01)
            self.ax.set_ylim(lo - pad, hi + pad)

        self.ax.set_xticks([])

        try:
            off_txt = "ao vivo" if off == 0 else f"{off} vela(s) atrás"
            self.ax.text(
                0.01, 0.02,
                f"Tempo da vela: {tf}s | Velas na tela: {bars} | Visualização: {off_txt}",
                transform=self.ax.transAxes,
                ha="left", va="bottom",
                color="#E5E7EB", fontsize=10, alpha=0.85,
            )
        except Exception:
            pass

        # >>> AJUSTE PRINCIPAL: dá espaço para o eixo da direita não cortar
        self.fig.subplots_adjust(left=0.012, right=0.960, top=0.92, bottom=0.10)

        try:
            self.ax.margins(x=0.01, y=0.03)
        except Exception:
            pass

        self.canvas.draw_idle()

    # =========================
    # Livro
    # =========================
    def _refresh_book(self) -> None:
        sym = self._selected_symbol.get()
        book = self._orderbook.get(sym)

        if not book:
            self._spread_var.set("Spread: —")
            for row in self._book_rows:
                row["sell"].configure(text="—")
                row["price"].configure(text="—")
                row["buy"].configure(text="—")
            return

        asks = book.get("asks", [])
        bids = book.get("bids", [])

        try:
            best_ask = float(asks[0]["price"]) if asks else 0.0
            best_bid = float(bids[0]["price"]) if bids else 0.0
            if best_ask and best_bid:
                self._spread_var.set(f"Spread: {(best_ask - best_bid):.2f}")
            else:
                self._spread_var.set("Spread: —")
        except Exception:
            self._spread_var.set("Spread: —")

        levels = min(len(asks), len(bids), len(self._book_rows))
        for i in range(len(self._book_rows)):
            if i < levels:
                a = asks[i]
                b = bids[i]
                self._book_rows[i]["sell"].configure(text=f"{float(a.get('qty', 0.0)):.0f}")
                self._book_rows[i]["price"].configure(text=f"{float(a.get('price', 0.0)):.2f}")
                self._book_rows[i]["buy"].configure(text=f"{float(b.get('qty', 0.0)):.0f}")
            else:
                self._book_rows[i]["sell"].configure(text="—")
                self._book_rows[i]["price"].configure(text="—")
                self._book_rows[i]["buy"].configure(text="—")

    # =========================
    # Notícias
    # =========================
    def _sentiment_label(self, x: float) -> str:
        if x <= -0.15:
            return f"Negativo ({x:+.2f})"
        if x >= 0.15:
            return f"Positivo ({x:+.2f})"
        return f"Neutro ({x:+.2f})"

    def _render_news(self) -> None:
        try:
            self.txt_news.configure(state="normal")
            self.txt_news.delete("1.0", "end")
        except Exception:
            return

        sym = self._selected_symbol.get()
        only_symbol = (self._news_filter_var.get() == "Somente este ativo")
        lang_filter = self._news_lang_filter_var.get().strip().upper()

        items = list(self._news_items)[-120:]
        count = 0

        for it in reversed(items):
            lang = str(it.get("language", "") or "").strip().upper()
            if lang_filter not in ("TODOS", "") and lang != lang_filter:
                continue

            tickers = it.get("tickers") or []
            hints = it.get("symbols_hint") or []
            related = (sym in tickers) or (sym in hints)

            if only_symbol and not related:
                continue

            count += 1
            ts = it.get("ts", "")
            source = it.get("source", "—")
            title = it.get("title", "")
            url = it.get("url", "")
            impact = float(it.get("impact", 0.0) or 0.0)
            sent = float(it.get("sentiment", 0.0) or 0.0)
            topics = it.get("topics") or []

            rel_txt = "Relacionado ao ativo" if related else "Geral"
            assets_txt = ", ".join((tickers[:6] if tickers else hints[:6])) if (tickers or hints) else "—"

            msg = (
                f"{ts} | Fonte: {source} | {rel_txt}\n"
                f"Sentimento: {self._sentiment_label(sent)} | Impacto: {impact:.2f} | Idioma: {lang or '—'}\n"
                f"Título: {title}\n"
                f"Ativos: {assets_txt}\n"
            )
            if topics:
                msg += f"Tópicos: {', '.join(topics[:6])}\n"
            if url:
                msg += f"Link: {url}\n"
            msg += "-" * 66 + "\n"

            self.txt_news.insert("end", msg)

        if count == 0:
            self.txt_news.insert(
                "end",
                "Nenhuma notícia encontrada com esses filtros.\nTente: Mostrar = Tudo, Idioma = Todos.\n",
            )

        self.txt_news.see("end")
        try:
            self.txt_news.configure(state="disabled")
        except Exception:
            pass

    # =========================
    # Pipeline
    # =========================
    def start(self) -> None:
        if self._runner_thread and self._runner_thread.is_alive():
            self._log("Já está rodando.")
            return

        ui_mode = self._mode.get().strip().lower()
        self.config.execution.mode = "paper" if ui_mode.startswith("sim") else "live"

        self._stop_event.clear()
        self._set_running_ui(True)
        self._log(f"Iniciando... modo={self._mode.get()} (interno: {self.config.execution.mode})")

        def _run():
            import asyncio
            import traceback

            try:
                asyncio.run(
                    run_market_pipeline(
                        self.config,
                        runtime_seconds=10 ** 9,
                        stop_event=self._stop_event,
                        event_queue=self._events,
                        command_queue=self._commands,
                    )
                )
            except Exception as e:
                # ✅ CAPTURA A MSG AQUI (não use "e" dentro de lambda sem capturar)
                err_msg = f"{type(e).__name__}: {e}"
                err_tb = traceback.format_exc()

                # Log seguro (sem depender do escopo do except)
                self.root.after(0, lambda m=err_msg: self._log(f"Erro no pipeline: {m}"))
                self.root.after(0, lambda t=err_tb: self._log(t))

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

    # =========================
    # Ordens (dupla confirmação)
    # =========================
    def _send_order(self, side: str) -> None:
        symbol = self._selected_symbol.get()
        side_pt = "COMPRAR" if side.upper() == "BUY" else "VENDER" if side.upper() == "SELL" else side.upper()
        if not (self._runner_thread and self._runner_thread.is_alive()):
            messagebox.showwarning("PULSE-TRADER", "Inicie o robô antes de enviar ordens.")
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
            f"CONFIRMAÇÃO 1/2 — {mode.upper()} — {side_pt} {symbol}",
            f"Ativo: {symbol}\nAção: {side_pt}\nQuantidade: {qty:.2f}\nPreço: {price:.2f}\nStop (SL): {sl:.2f}\nAlvo (TP): {tp:.2f}\n\nConfirma o envio?",
        ):
            return

        text = simpledialog.askstring("CONFIRMAÇÃO 2/2", "Digite CONFIRMAR para enviar:", parent=self.root)
        if (text or "").strip().upper() != "CONFIRMAR":
            self._log("Ordem cancelada (confirmação 2/2).")
            return

        self._commands.put(
            {
                "type": "ORDER",
                "symbol": symbol,
                "side": side,
                "qty": float(qty),
                "sl": float(sl),
                "tp": float(tp),
                "confidence": float(conf),
                "reason": "manual_ui",
            }
        )
        self._log(f"Ordem enviada: {side_pt} {symbol} qty={qty:.2f} (modo={self._mode.get()})")

    def _get_last_price(self, symbol: str) -> Optional[float]:
        dq = self._candles.get(symbol)
        if not dq:
            return None
        return float(dq[-1].get("close", 0.0))

    def _compute_qty(self, symbol: str, price: float) -> float:
        if self._use_risk_var.get():
            sig = self._last_signal.get(symbol)
            atr_val = float(sig.get("meta", {}).get("atr", max(price * 0.002, 1.0))) if sig else max(price * 0.002, 1.0)
            stop_dist = max(atr_val * 1.0, price * 0.001)
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

    # =========================
    # Events
    # =========================
    def _poll_events(self) -> None:
        """Consome eventos da pipeline e atualiza a UI.

        ⚠️ Se uma exception escapar daqui, o `after()` não é reagendado e
        a interface parece que "parou". Por isso o reagendamento fica no finally.
        """

        try:
            processed = 0
            while processed < 350:
                try:
                    ev = self._events.get_nowait()
                except Empty:
                    break

                processed += 1
                et = ev.get("type")
                payload = ev.get("payload", {}) or {}

                if et == "status":
                    self._set_running_ui(bool(payload.get("running", False)))

                elif et == "candle":
                    sym = payload.get("symbol", "")
                    if not sym:
                        continue

                    dq = self._candles.setdefault(sym, deque(maxlen=self._max_candles))
                    dq.append(payload)

                    if self._follow_live_var.get():
                        self._view_offset_var.set(0)

                    if sym == self._selected_symbol.get():
                        self._k_price.set(f"{float(payload.get('close', 0.0)):.2f}")
                        self._refresh_chart()

                elif et == "orderbook":
                    sym = payload.get("symbol", "")
                    book = payload.get("book")
                    if sym and book:
                        self._orderbook[sym] = book
                        if sym == self._selected_symbol.get():
                            self._refresh_book()

                elif et == "news":
                    it = {
                        "ts": str(payload.get("ts", ""))[-8:] or time.strftime("%H:%M:%S"),
                        "title": str(payload.get("title", "")),
                        "source": str(payload.get("source", "")),
                        "url": str(payload.get("url", "")),
                        "language": str(payload.get("language", "")),
                        "sentiment": float(payload.get("sentiment", 0.0) or 0.0),
                        "impact": float(payload.get("impact", 0.0) or 0.0),
                        "tickers": list(payload.get("tickers", []) or []),
                        "topics": list(payload.get("topics", []) or []),
                        "symbols_hint": list(payload.get("symbols_hint", []) or []),
                    }
                    self._news_items.append(it)
                    self._render_news()

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
                            self._k_reco.set(
                                "COMPRAR" if side == "BUY" else "VENDER" if side == "SELL" else "ESPERAR"
                            )
                            self._k_conf.set(self._fmt_percent(conf))

                        ts = str(payload.get("ts", ""))[-8:] or time.strftime("%H:%M:%S")
                        side_raw = str(payload.get("side", "WAIT")).upper()
                        side_label = "COMPRAR" if side_raw == "BUY" else "VENDER" if side_raw == "SELL" else "ESPERAR"
                        tag = "BUY" if side_raw == "BUY" else "SELL" if side_raw == "SELL" else "WAIT"

                        self.tree.insert(
                            "",
                            "end",
                            values=(
                                ts,
                                sym,
                                "SINAL",
                                side_label,
                                self._fmt_percent(float(payload.get("confidence", 0.0))),
                                f"{float(payload.get('price', 0.0)):.2f}",
                                "OK",
                            ),
                            tags=(tag,),
                        )
                        self.tree.yview_moveto(1)

                elif et == "execution":
                    sym = str(payload.get("symbol", ""))
                    ts = str(payload.get("ts", ""))[-8:] or time.strftime("%H:%M:%S")
                    side = str(payload.get("side", "")).upper()
                    price = float(payload.get("filled_price", 0.0))
                    status = str(payload.get("status", ""))
                    tag = "BUY" if side == "BUY" else "SELL" if side == "SELL" else "WAIT"

                    self.tree.insert(
                        "",
                        "end",
                        values=(ts, sym, "EXECUÇÃO", side, "—", f"{price:.2f}", status),
                        tags=(tag,),
                    )
                    self.tree.yview_moveto(1)
                    try:
                        cur = int(self._k_trades.get())
                    except Exception:
                        cur = 0
                    self._k_trades.set(str(cur + 1))

                elif et == "shadow_position":
                    sym = str(payload.get("symbol", ""))
                    if sym:
                        self._shadow_pos[sym] = payload
                        if sym == self._selected_symbol.get():
                            self._refresh_chart()

                elif et == "shadow_trade":
                    sym = str(payload.get("symbol", ""))
                    if sym:
                        r = payload.get("r_multiple")
                        rr = (f"R={float(r):.2f}" if r is not None else "R=?")
                        self._log(
                            f"Shadow trade fechado: {sym} {payload.get('side')} {payload.get('exit_reason')} | {rr}"
                        )
                        if sym == self._selected_symbol.get():
                            self._refresh_chart()

                elif et == "performance":
                    try:
                        win_rate = float(payload.get("win_rate", 0.0))
                        avg_r = float(payload.get("avg_r", 0.0))
                        self._k_winrate.set(self._fmt_percent(win_rate))
                        self._k_avg_r.set(f"{avg_r:.3f}")
                    except Exception:
                        pass

                elif et == "log":
                    self._log(str(payload.get("msg", "")))

        except Exception as e:
            # Não deixa a UI "morrer" silenciosamente
            try:
                self._log(f"[UI] Erro no _poll_events: {type(e).__name__}: {e}")
            except Exception:
                pass

        finally:
            # sempre reageenda, a menos que a janela tenha sido destruída
            try:
                if self.root.winfo_exists():
                    self.root.after(140, self._poll_events)
            except Exception:
                pass

    def _fmt_percent(self, x: float) -> str:
        # ex.: 0.735 -> 73,5%
        try:
            val = float(x) * 100.0
        except Exception:
            return "—"
        return (f"{val:.1f}%").replace(".", ",")

    def _refresh_all(self) -> None:
        sym = self._selected_symbol.get()
        self._k_newsimpact.set(f"{float(self._news_impact.get(sym, 0.0)):.2f}")
        self._refresh_chart()
        self._refresh_book()

    # =========================
    # Run
    # =========================
    def run(self) -> None:
        self.root.mainloop()


def launch_dashboard() -> None:
    TradingDashboard().run()
