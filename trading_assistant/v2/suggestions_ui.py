"""Multi-asset technical suggestions for the PAPER desktop application."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime
from pathlib import Path
import json

from .backtest import save_report
from .data import CSVProvider, CandleStore, SyntheticProvider, export_csv
from .models import UTC
from .session import local_time
from .suggestions import analyze_series, matches_profile, merge_series, save_plan, TRENDS, SETUPS, STRATEGIES
from .data_center import DataCenter
from .company_context import summarize_context


class SuggestionsPanel:
    PROFILES = {"No dia · minutos e horas": "intraday", "Dias e semanas · diário": "swing"}

    def __init__(self, parent, dashboard):
        self.dashboard = dashboard
        self.frame = ttk.Frame(parent, padding=12)
        parent.add(self.frame, text="Sugestões")
        self.catalog_path = dashboard.data_dir / "suggestions.sqlite"
        self.series = {}
        self.rows = {}
        self.mode = "catalog"
        self.signature = None
        self.context_reviewed=tk.BooleanVar(value=False)
        self.review_signature=None
        self.warming_up=False
        self.profile = tk.StringVar(value=next(iter(self.PROFILES)))
        self.notice = tk.StringVar(value="Importe históricos autorizados ou analise os candles já encerrados no replay.")
        self.headline = tk.StringVar(value="Selecione um ativo para ver o cenário")

        bar = ttk.Frame(self.frame)
        bar.pack(fill="x")
        ttk.Label(bar, text="HORIZONTE", style="Section.TLabel").pack(side="left", padx=(0, 8))
        combo = ttk.Combobox(bar, textvariable=self.profile, values=tuple(self.PROFILES), state="readonly", width=30)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _: dashboard.guard(self.analyze))
        ttk.Label(bar, text="▲ Alta   ▼ Baixa   ● Lateral", style="Section.TLabel").pack(side="right", padx=8)
        controls = ttk.Frame(self.frame)
        controls.pack(fill="x", pady=3)
        self.import_button = dashboard._button(controls, "Adicionar CSVs", self.import_csvs)
        self.replay_button = dashboard._button(controls, "Usar replay atual", self.use_replay)
        dashboard._button(controls, "Dados salvos", self.load_catalog)
        self.demo_button = dashboard._button(controls, "Exemplo simulado", self.load_demo)
        dashboard._button(controls, "Atualizar análise", self.analyze)
        dashboard._button(controls, "Fontes e atualização", lambda:self.data_center.open(), side="right")
        ttk.Label(self.frame, text="Cenários em histórico · sem cotação ao vivo · probabilidade só com calibração aprovada.",
                  style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        message = ttk.Label(self.frame, textvariable=self.notice, wraplength=1100)
        message.pack(fill="x", pady=(0, 8))
        message.bind("<Configure>", lambda e: message.configure(wraplength=max(260, e.width - 12)))

        panes = ttk.Panedwindow(self.frame, orient="vertical")
        panes.pack(fill="both", expand=True)
        listing = ttk.Frame(panes)
        panes.add(listing, weight=1)
        columns = ("symbol", "trend", "setup", "entry", "stop", "target", "source", "reference")
        self.table = ttk.Treeview(listing, columns=columns, show="headings", height=4, selectmode="browse")
        for col, title, width in zip(columns,
                ("Ativo / período", "Tendência", "Entrada", "Preço sugerido", "Stop", "Alvo", "Origem", "Último candle encerrado"),
                (130, 110, 140, 105, 100, 100, 150, 175)):
            self.table.heading(col, text=title)
            self.table.column(col, width=width, minwidth=75, stretch=True, anchor="w")
        self.table.grid(row=0, column=0, sticky="nsew")
        vscroll = ttk.Scrollbar(listing, orient="vertical", command=self.table.yview)
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll = ttk.Scrollbar(listing, orient="horizontal", command=self.table.xview)
        hscroll.grid(row=1, column=0, sticky="ew")
        self.table.configure(xscrollcommand=hscroll.set)
        self.table.configure(yscrollcommand=vscroll.set)
        listing.rowconfigure(0, weight=1)
        listing.columnconfigure(0, weight=1)
        self.table.bind("<<TreeviewSelect>>", lambda _: self.show_selected())

        details = ttk.Frame(panes, padding=(0, 8, 0, 0))
        panes.add(details, weight=1)
        self.heading = ttk.Label(details, textvariable=self.headline, font=("Segoe UI Semibold", 14))
        self.heading.pack(anchor="w", pady=(0, 5))
        text_frame = ttk.Frame(details)
        text_frame.pack(fill="both", expand=True)
        self.detail = tk.Text(text_frame, height=5, wrap="word", relief="flat", font=("Segoe UI", 10),
                              padx=10, pady=8, state="disabled")
        self.detail.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.review_button=ttk.Checkbutton(details,text='Revisei os alertas corporativos desta proposta',variable=self.context_reviewed)
        self.review_button.pack(side='bottom',anchor='w',before=text_frame)
        footer = ttk.Frame(self.frame)
        footer.pack(side="bottom", fill="x", pady=(5, 0), before=panes)
        self.save_button = dashboard._button(footer, "Guardar plano PAPER", self.store_selected, style="Accent.TButton")
        dashboard._button(footer,'Levar ao replay',self.load_selected_replay)
        self.arm_button=dashboard._button(footer,'Armar entrada PAPER',self.arm_selected)
        dashboard._button(footer,'Cancelar plano',self.cancel_selected)
        dashboard._button(footer,'Validar histórico',self.validate_selected)
        dashboard._button(footer, "Exportar sugestões", self.export, side="right")
        self.load_catalog()
        self.data_center=DataCenter(self)

    @staticmethod
    def price(value):
        return "—" if value is None else f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    @staticmethod
    def period(seconds):
        return "diário" if seconds == 86400 else f"{seconds // 60} min" if seconds % 60 == 0 else f"{seconds} s"

    def _load_saved(self):
        store = CandleStore(self.catalog_path)
        try:
            keys = store.db.execute("SELECT DISTINCT symbol,seconds,source FROM candles ORDER BY symbol,seconds,source").fetchall()
            return {tuple(key): store.load(*key) for key in keys}
        finally:
            store.close()

    def load_catalog(self):
        self.series = self._load_saved()
        self.mode = "catalog"
        self.analyze()

    def import_csvs(self):
        paths = filedialog.askopenfilenames(parent=self.dashboard.root, title="Históricos autorizados · vários ativos", filetypes=[("CSV", "*.csv")])
        if not paths:
            return
        # Parse every file before changing the saved catalog; inserts/revisions are atomic.
        bars = [bar for path in paths for bar in CSVProvider(path).bars()]
        self.add_bars(bars)

    def add_bars(self,bars):
        merge_series(self._load_saved(), bars)
        store = CandleStore(self.catalog_path)
        try:
            store.put(bars)
        finally:
            store.close()
        self.load_catalog()

    def use_replay(self):
        self.mode = "replay"
        if self.dashboard.bars:
            profile = "swing" if self.dashboard.bars[-1].seconds == 86400 else "intraday"
            self.profile.set(next(label for label, value in self.PROFILES.items() if value == profile))
        self.signature = None
        self.analyze()

    def load_demo(self):
        self.series = {}
        for symbol, seconds in (("WIN", 60), ("WDO", 60), ("PETR4", 86400), ("VALE3", 86400)):
            bars = SyntheticProvider(symbol, 100, seconds=seconds).bars()
            self.series[(symbol, seconds, "SYNTHETIC")] = bars
        self.mode = "demo"
        self.analyze()

    def analyze(self):
        profile = self.PROFILES[self.profile.get()]
        if self.mode == "replay":
            bars = self.dashboard.bars
            series = {(bars[-1].symbol, bars[-1].seconds, bars[-1].source): bars} if bars else {}
            cutoff = self.dashboard.now()
        else:
            series = self.series
            cutoff = datetime.now(UTC)
        previous = self.selected()
        self.rows = {}
        self.table.delete(*self.table.get_children())
        analyses = [analyze_series(bars, profile, as_of=cutoff, parameters=self.dashboard.engine.strategy,
                                  instruments=self.dashboard.engine.specs)
                    for (_, seconds, _), bars in sorted(series.items()) if matches_profile(seconds, profile)]
        priority = {"CONFIRMED": 0, "CONDITIONAL": 1, "WAIT": 2, "INSUFFICIENT": 3}
        analyses.sort(key=lambda s: (priority[s.setup], s.symbol, s.seconds, s.source))
        selected = None
        for i, s in enumerate(analyses):
            key = str(i)
            self.rows[key] = s
            reference = local_time(s.closed_at).strftime("%d/%m/%Y %H:%M") if s.closed_at else "Sem candle fechado"
            self.table.insert("", "end", iid=key, tags=(s.trend,), values=(
                f"{s.symbol} · {self.period(s.seconds)}", TRENDS[s.trend],
                SETUPS[s.setup] + (" · compra" if s.side == "BUY" else " · venda" if s.side == "SELL" else ""),
                self.price(s.entry), self.price(s.stop), self.price(s.target), s.source, reference))
            if previous and (s.symbol, s.seconds, s.source) == (previous.symbol, previous.seconds, previous.source):
                selected = key
        origin = {"replay": "Somente candles já processados no replay", "demo": "EXEMPLO SINTÉTICO · sem dados de mercado", "catalog": "Históricos importados e salvos neste computador"}[self.mode]
        self.notice.set(f"{origin}. {len(analyses)} séries neste perfil. " +
                        ("Confira a data de cada cenário." if analyses else "Use candles intradiários para No dia ou diários (86400 s) para Dias e semanas; mínimo de 35 candles encerrados."))
        if self.rows:
            self.table.selection_set(selected or next(iter(self.rows)))
        self.show_selected()

    def context_for(self,s):
        import re
        if not re.fullmatch(r'[A-Z0-9]{2,16}',s.symbol):
            return {'lines':['Identificação do ativo não configurada para contexto de empresas.'],'included':False,'review_required':True}
        path=self.dashboard.data_dir/'company-context'/(s.symbol+'.json')
        if not path.exists():
            return {'lines':['Fundamentos/comunicados não carregados; este cenário usa apenas preço e volume.'],
                    'included':False,'review_required':s.profile=='swing'}
        snapshot=json.loads(path.read_text(encoding='utf-8'))
        cutoff=self.dashboard.now() if self.mode=='replay' else datetime.now(UTC)
        return summarize_context(snapshot,as_of=cutoff,side=s.side)

    def selected_plan(self):
        s=self.selected()
        if s is None:return None
        plans=[plan for plan in self.dashboard.ledger.read().get('analysis_plans',{}).values()
               if plan['analysis']['data_sha256']==s.data_sha256 and plan['analysis']['profile']==s.profile]
        return max(plans,key=lambda plan:plan['saved_at']) if plans else None

    def replay_changed(self):
        if self.mode != "replay":
            return
        bars = self.dashboard.bars
        signature = (bars[-1] if bars else None, len(bars), self.dashboard.engine.strategy)
        if signature != self.signature:
            self.signature = signature
            self.analyze()

    def selected(self):
        selection = self.table.selection()
        return self.rows.get(selection[0]) if selection else None

    def show_selected(self):
        s = self.selected()
        self.save_button.configure(state="normal" if s and s.entry is not None else "disabled")
        self.arm_button.configure(state='normal' if s and s.entry is not None and self.mode=='replay' and not self.warming_up else 'disabled')
        self.review_button.configure(state='normal' if s and s.profile=='swing' else 'disabled')
        if s is None:
            self.headline.set("Selecione um ativo para ver o cenário")
            text = "Adicione CSVs de vários ativos, use o replay atual ou abra o exemplo simulado.\nCada perfil usa seu próprio período de dados. Candles ainda abertos ficam fora da análise."
        else:
            self.headline.set(f"{TRENDS[s.trend]}  ·  {s.symbol}  ·  {SETUPS[s.setup]}")
            self.heading.configure(foreground=self.colors[s.trend] if hasattr(self, "colors") else "#91a5bf")
            action = {"BUY": "Compra proposta", "SELL": "Venda proposta", None: "Aguardar"}[s.side]
            reference = local_time(s.closed_at).strftime("%d/%m/%Y %H:%M:%S") if s.closed_at else "indisponível"
            text = f"Motivo: {s.reason}\n\n{s.condition}\n"
            if s.entry is not None:
                rr = abs(s.target - s.entry) / abs(s.entry - s.stop)
                text += (f"\n{action} · Estratégia: {STRATEGIES[s.strategy]} · Entrada de referência: {self.price(s.entry)}"
                         f" · Stop: {self.price(s.stop)} · Alvo: {self.price(s.target)} · Retorno/risco bruto: {rr:.2f}\n"
                         f"Orçamento configurado por operação: {self.dashboard._brl(self.dashboard.limits.capital * self.dashboard.limits.risk_fraction)}. "
                         "Quantidade e aprovação de risco ainda pendentes; custos e gaps alteram o resultado.\n")
            text += (f"\nOrigem: {s.source} · Candle encerrado até {reference} (Brasília) · {s.candles} candles. "
                     "Cenário técnico por regras; modelos estatísticos, quando disponíveis, aparecem abaixo. Guardar um plano não envia uma ordem.")
            if s.profile == "swing":
                context=self.context_for(s)
                signature=(s.data_sha256,json.dumps(context,sort_keys=True))
                if signature!=self.review_signature:
                    self.context_reviewed.set(False);self.review_signature=signature
                text+='\n\nCONTEXTO DA EMPRESA\n'+'\n'.join(context['lines'])
                text+='\nFundamentos e comunicados geram alertas de revisão; não são um percentual de valorização. Proventos e aluguel não estão no P&L do simulador.'
            model_path=self.dashboard.data_dir/'models'/f'{s.symbol}-{s.seconds}.json'
            if s.symbol in self.dashboard.engine.specs and model_path.exists():
                from .ml import predict
                cutoff=self.dashboard.now() if self.mode=='replay' else datetime.now(UTC)
                model=json.loads(model_path.read_text(encoding='utf-8'))
                if datetime.fromisoformat(model.get('created_at',model['train_end']))>cutoff:
                    text+='\nModelo atual excluído deste replay: foi treinado depois da data simulada.'
                else:
                    bars=self.dashboard.bars if self.mode=='replay' else self.series.get((s.symbol,s.seconds,s.source),[])
                    try:
                        estimate=predict(model,bars)
                        if estimate.get('probability_up') is not None:
                            text+=f"\nEstimativa do modelo para alta no horizonte de {model['horizon']} candle(s): {estimate['probability_up']:.1%}; calibração histórica aprovada, sujeita a deterioração."
                        else:text+='\nModelo sem calibração aprovada para este cenário; probabilidade de alta/baixa indisponível.'
                        if estimate['degraded']:text+=' Indicadores fora da distribuição de treino; revisar o modelo.'
                    except (ValueError,IndexError):text+='\nModelo salvo incompatível com os dados selecionados; refaça a validação.'
            plan=self.selected_plan()
            if plan:text+=f"\n\nPlano guardado: {plan['state']} · Quantidade: {plan.get('quantity') or 'a validar'}."
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def store_selected(self):
        s = self.selected()
        if s is None:
            raise ValueError("Selecione um cenário")
        plan = save_plan(self.dashboard.ledger, s, saved_at=datetime.now(UTC), limits=self.dashboard.limits,
                         costs=self.dashboard.costs, parameters=self.dashboard.engine.strategy,
                         instruments=self.dashboard.engine.specs,
                         context=self.context_for(s) if s.profile=='swing' else None,context_ack=self.context_reviewed.get() if s.profile=='swing' else False)
        self.notice.set(f"Plano {plan['id'][:8]} de {s.symbol} guardado no SQLite local. Proposta sem ordem; quantidade e risco precisam de validação antes de qualquer entrada PAPER.")
        self.show_selected()
        return plan

    def arm_selected(self):
        if self.warming_up:raise ValueError('Aguarde a preparação do replay')
        if self.mode!='replay':raise ValueError('Use o replay atual para vincular a entrada ao histórico correto')
        plan=self.store_selected()
        result=self.dashboard.engine.arm_plan(plan['id'],self.dashboard.now())
        self.notice.set(f"Plano {result['state']} · entradas passam pelo risco central e só preenchem em candle posterior. Gatilhos condicionais exigem Simulação automática ligada.")
        self.dashboard.refresh();self.show_selected()

    def load_selected_replay(self):
        from .models import aware
        from datetime import timedelta
        s=self.selected()
        if not s:raise ValueError('Selecione um ativo')
        if self.warming_up:raise ValueError('Preparação do replay em andamento')
        if s.symbol not in self.dashboard.engine.specs:raise ValueError('Configure a especificação do ativo antes de carregar o replay')
        bars=list(self.dashboard.bars if self.mode=='replay' else self.series[(s.symbol,s.seconds,s.source)])
        bars=[b for b in bars if aware(b.ts)+timedelta(seconds=b.seconds)<=aware(s.closed_at)]
        d=self.dashboard;d._can_load()
        last=d.ledger.read()['last_bars'].get(s.symbol)
        if last and datetime.fromisoformat(last)>aware(s.closed_at):
            raise ValueError('O ledger já avançou além deste cenário; use um histórico posterior ou outro diretório de dados')
        folder=d.data_dir/'downloads';folder.mkdir(exist_ok=True)
        path=folder/f'replay-{s.symbol}-{s.seconds}-{s.data_sha256[:12]}.csv';export_csv(bars,path)
        provider=CSVProvider(path)
        d.feed=bars;d.symbol.set(s.symbol)
        with d.ledger.transaction() as state:state['feed']={'kind':'csv','path':str(path.resolve()),'sha256':provider.sha256}
        d._resume();self.mode='replay';self.signature=None;self.warming_up=True
        engine=d.engine
        def chunk():
            state=d.ledger.read()
            if d.engine is not engine or state['positions'] or any(o['status']=='NEW' for o in state['orders'].values()):
                self.warming_up=False;self.notice.set('Preparação interrompida por mudança de configuração ou exposição aberta.');self.show_selected();return
            for _ in range(25):
                if d.cursor>=len(d.feed):break
                b=d.feed[d.cursor];engine.on_bar(b,automatic=False);d.cursor+=1
                d.bars.append(b);d.bars=d.bars[-1000:]
            d.refresh()
            if d.cursor<len(d.feed):
                self.notice.set(f'Preparando replay sem entradas: {d.cursor}/{len(d.feed)} candles…')
                d.root.after(1,lambda:d.guard(chunk))
            else:
                self.warming_up=False;self.analyze()
                self.notice.set('Replay preparado até o cenário. Confira o plano e arme a entrada PAPER para os próximos candles.')
        d.root.after(1,lambda:d.guard(chunk))

    def cancel_selected(self):
        plan=self.selected_plan()
        if not plan:raise ValueError('Nenhum plano guardado para este cenário')
        self.dashboard.engine.cancel_plan(plan['id'],self.dashboard.now())
        self.notice.set('Plano cancelado. Posições já executadas exigem gerenciamento próprio.')
        self.dashboard.refresh();self.show_selected()

    def validate_selected(self):
        from .validation import validate_history
        s=self.selected()
        if not s:raise ValueError('Selecione um ativo')
        bars=list(self.dashboard.bars if self.mode=='replay' else self.series[(s.symbol,s.seconds,s.source)])
        path=filedialog.asksaveasfilename(parent=self.dashboard.root,defaultextension='.json',initialfile=f'validacao-{s.symbol}.json')
        if not path:return
        engine=self.dashboard.engine;cutoff=self.dashboard.now() if self.mode=='replay' else datetime.now(UTC)
        limits,costs,calendar,specs=engine.limits,engine.costs,engine.calendar,dict(engine.specs)
        def done(report):
            save_report(report,path)
            model_dir=self.dashboard.data_dir/'models';model_dir.mkdir(exist_ok=True)
            save_report(report['ml'],model_dir/f'{s.symbol}-{s.seconds}.json')
            self.notice.set(report['verdict']+' · relatório: '+path)
        self.dashboard.jobs.start(lambda:validate_history(bars,limits=limits,costs=costs,calendar=calendar,instruments=specs,now=cutoff),done)
        self.notice.set('Validando em segundo plano: seleção temporal, holdout, custos e modelo estatístico…')

    def export(self):
        if not self.rows:
            raise ValueError("Não há sugestões neste perfil")
        path = filedialog.asksaveasfilename(parent=self.dashboard.root, defaultextension=".json", initialfile="pulse-sugestoes.json")
        if path:
            save_report({"mode": "PAPER_ANALYSIS", "profile": self.PROFILES[self.profile.get()],
                         "analyses": [s.to_dict() for s in self.rows.values()]}, path)
            self.notice.set("Sugestões exportadas: " + path)

    def apply_theme(self, dark):
        self.colors = {"UP": "#67d3a3" if dark else "#137348", "DOWN": "#ff929d" if dark else "#ac2438",
                       "FLAT": "#ffd27b" if dark else "#825d12", "UNKNOWN": "#91a5bf" if dark else "#52667f"}
        for trend, color in self.colors.items():
            self.table.tag_configure(trend, foreground=color)
        self.detail.configure(bg="#111e30" if dark else "#ffffff", fg="#edf3fc" if dark else "#17273d")
        self.show_selected()

    def show_sources(self):
        import webbrowser
        window = tk.Toplevel(self.dashboard.root)
        window.title("Dados para as sugestões")
        window.geometry("760x410")
        ttk.Label(window, padding=16, wraplength=710, justify="left", text=(
            "NO DIA: use histórico de minutos/horas exportado do Profit, conforme sua licença.\n\n"
            "DIAS E SEMANAS: use candles diários de uma fonte autorizada; dados da CVM podem complementar estudos de empresas. "
            "Esta aba calcula apenas cenários técnicos de preço/volume.\n\n"
            "CSV padrão: symbol,ts,open,high,low,close,volume,source,seconds. Use volume em quantidade, "
            "data de abertura com fuso e origem verdadeira. Para candles diários use seconds=86400 e respeite a convenção de encerramento. "
            "Arquivos brutos do Profit precisam ser convertidos para esse formato. Importe arquivos separados para períodos diferentes do mesmo ativo.\n\n"
            "Os botões abaixo abrem instruções oficiais. Fontes e atualização permite consultas públicas e atualização histórica somente de leitura."
        )).pack(fill="x")
        for label, url in (("Como exportar histórico do Profit", "https://ajuda.nelogica.com.br/hc/pt-br/articles/360044287672-Como-exportar-dados-hist%C3%B3ricos-de-ativos-para-o-Excel"),
                           ("Dados de empresas na CVM", "https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr")):
            ttk.Button(window, text=label, command=lambda link=url: webbrowser.open(link)).pack(anchor="w", padx=16, pady=4)
