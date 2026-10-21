from __future__ import annotations
import json
import os
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from datetime import datetime,timedelta
from pathlib import Path
from dataclasses import asdict,fields
from statistics import mean
try:
    from PIL import Image,ImageDraw,ImageTk
except ImportError:
    Image=ImageDraw=ImageTk=None
from .models import Limits,ExecutionSettings,Decision,Instrument,INSTRUMENTS,UTC
from .data import SyntheticProvider,CSVProvider,aggregate,CandleStore
from .execution import PaperEngine
from .ledger import Ledger
from .strategy import Strategy
from .backtest import metrics,run_backtest,save_report
from .chart_raster import antialiased_lines_png
from .session import local_time
from .session import SessionCalendar
from .suggestions_ui import SuggestionsPanel
from .jobs import BackgroundJobs
from . import __version__

class Dashboard:
    def __init__(self,data_dir=None):
        # Ask Windows for physical display pixels before creating a Tk window.
        # Tk then scales fonts and controls to the monitor's DPI.
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError, ValueError):
                pass
        try:
            import customtkinter as ctk
            ctk.set_appearance_mode("dark");self.root=ctk.CTk()
        except ImportError:
            self.root=tk.Tk()
        self.root.title(f"PULSE-TRADER {__version__} | PAPER")
        scale=self.root._get_window_scaling() if hasattr(self.root,"_get_window_scaling") else 1.
        available_width=max(640,int((self.root.winfo_screenwidth()-40)/scale))
        available_height=max(480,int((self.root.winfo_screenheight()-100)/scale))
        self.root.geometry(f"{min(1380,available_width)}x{min(850,available_height)}+12+12")
        self.root.minsize(min(1050,available_width),min(690,available_height))
        self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.data_dir=Path(data_dir or os.getenv("PULSE_DATA_DIR","runtime"));self.data_dir.mkdir(parents=True,exist_ok=True)
        self.ledger=Ledger(self.data_dir/"paper.sqlite")
        config=self.ledger.read().get("config",{})
        self.limits=Limits(**config.get("limits",{}));self.costs=ExecutionSettings(**config.get("costs",{}))
        calendar=SessionCalendar.from_config(config["calendar"]) if config.get("calendar") is not None else None
        specs={key:Instrument(**value) for key,value in config['instruments'].items()} if config.get('instruments') else None
        self.engine=PaperEngine(self.ledger,self.limits,self.costs,instruments=specs,strategy=Strategy(**config.get("strategy",{})),calendar=calendar)
        self.bars=[];self.feed=[];self.cursor=0;self.running=False;self.timer=None
        self.window=70;self.offset=0;self.dark=True;self._chart_image=None
        self.symbol=tk.StringVar(value="WIN");self.strategy=tk.StringVar(value="trend")
        self._period_seconds={"1 min":60,"5 min":300,"15 min":900}
        self.timeframe=tk.StringVar(value="1 min");self.auto=tk.BooleanVar(value=True)
        self.status=tk.StringVar(value="PAPER | Fonte: SYNTHETIC | Sem conexão com corretora")
        self.jobs=BackgroundJobs(self.root,self.background_error)
        self.summary=tk.StringVar();self.signal_text=tk.StringVar(value="Aguardando 35 candles fechados. Confiança estatística: indisponível.")
        self.metrics={key:tk.StringVar(value="—") for key in ("capital","day","exposure","positions","trades","emergency")}
        self._build();self._theme();self._restore_feed();self.refresh()

    def _button(self,parent,text,command,style="TButton",side="left"):
        b=ttk.Button(parent,text=text,command=lambda:self.guard(command),style=style)
        b.pack(side=side,padx=4,pady=5)
        return b

    def guard(self,fn):
        try:return fn()
        except Exception as e:
            self.pause();self.status.set("BLOQUEADO: "+str(e));messagebox.showerror("PULSE-TRADER",str(e),parent=self.root)

    def background_error(self,error):
        self.status.set('Tarefa interrompida: '+str(error))
        messagebox.showerror('PULSE-TRADER',str(error),parent=self.root)

    def _build(self):
        top=ttk.Frame(self.root,padding=(18,12));top.pack(fill="x")
        ttk.Label(top,text="PULSE",style="Brand.TLabel").pack(side="left")
        ttk.Label(top,text=" / TRADER",style="BrandMuted.TLabel").pack(side="left")
        self._button(top,"Alternar tema",self.toggle_theme,side="right")
        ttk.Label(top,text=f"PAPER  •  {__version__}",style="Badge.TLabel").pack(side="right",padx=14)
        ttk.Label(self.root,textvariable=self.status,style="Status.TLabel").pack(fill="x",padx=20,pady=(0,12))

        overview=ttk.Frame(self.root);overview.pack(fill="x",padx=16,pady=(0,10))
        for i,(key,label) in enumerate((("capital","CAPITAL"),("day","RESULTADO DO DIA"),
                                       ("exposure","RISCO ABERTO"),("positions","POSIÇÕES"),
                                       ("trades","OPERAÇÕES"),("emergency","SEGURANÇA"))):
            overview.columnconfigure(i,weight=1,uniform="metrics")
            card=ttk.Frame(overview,style="Metric.TFrame",padding=(12,8))
            card.grid(row=0,column=i,sticky="nsew",padx=4)
            ttk.Label(card,text=label,style="MetricLabel.TLabel").pack(anchor="w")
            ttk.Label(card,textvariable=self.metrics[key],style="MetricValue.TLabel").pack(anchor="w",pady=(3,0))

        toolbar=ttk.Frame(self.root,padding=(12,3));toolbar.pack(fill="x",padx=16)
        source=ttk.Frame(toolbar);source.pack(fill="x")
        ttk.Label(source,text="ATIVO",style="Section.TLabel").pack(side="left",padx=(4,8))
        self.asset_combo=ttk.Combobox(source,textvariable=self.symbol,values=list(self.engine.specs),width=10,state="readonly")
        self.asset_combo.pack(side="left",padx=4)
        self._button(source,"Carregar simulação",self.load_synthetic)
        self._button(source,"Importar CSV",self.import_csv)
        playback=ttk.Frame(toolbar);playback.pack(fill="x")
        self._button(playback,"Iniciar replay",self.start,style="Accent.TButton")
        self._button(playback,"Pausar",self.pause)
        self._button(playback,"Próximo candle",self.step)
        ttk.Checkbutton(playback,text="Simulação automática",variable=self.auto).pack(side="left",padx=12)
        self._button(playback,"PARADA DE EMERGÊNCIA",lambda:self.emergency(True),style="Danger.TButton",side="right")

        self.tabs=ttk.Notebook(self.root);self.tabs.pack(fill="both",expand=True,padx=20,pady=(6,14))
        charttab=ttk.Frame(self.tabs,padding=(12,8));self.tabs.add(charttab,text="Mercado e sinais")
        controls=ttk.Frame(charttab);controls.pack(fill="x")
        ttk.Label(controls,text="GRÁFICO  /  REPLAY HISTÓRICO",style="Section.TLabel").pack(side="left",padx=(4,15))
        self._button(controls,"Zoom +",lambda:self.zoom(.75))
        self._button(controls,"Zoom −",lambda:self.zoom(1.3))
        self._button(controls,"← Anterior",lambda:self.pan(20))
        self._button(controls,"Mais recente →",lambda:self.pan(-20))
        ttk.Label(controls,text="Cada candle",style="Section.TLabel").pack(side="left",padx=(12,6))
        self.period_combo=ttk.Combobox(controls,textvariable=self.timeframe,
                                       values=tuple(self._period_seconds),width=8,state="readonly")
        self.period_combo.pack(side="left");self.period_combo.bind("<<ComboboxSelected>>",lambda _:self.change_period())
        self.chart=tk.Canvas(charttab,highlightthickness=0,height=390)
        self.chart.pack(fill="both",expand=True,pady=(8,5))
        self.chart.bind("<Configure>",lambda _:self.draw())
        self.chart.bind("<MouseWheel>",lambda e:self.zoom(.85 if e.delta>0 else 1.2))
        self.signal_label=ttk.Label(charttab,textvariable=self.signal_text,style="Signal.TLabel",wraplength=1050)
        self.signal_label.pack(fill="x",padx=4,pady=7)
        self.signal_label.bind("<Configure>",lambda e:self.signal_label.configure(wraplength=max(260,e.width-24)))
        manual=ttk.Frame(charttab);manual.pack(fill="x")
        self._button(manual,"Compra PAPER por risco",lambda:self.manual("BUY"))
        self._button(manual,"Venda PAPER por risco",lambda:self.manual("SELL"))
        self._button(manual,"Zerar posições PAPER",self.flatten)
        self._button(manual,"Cancelar ordens pendentes",self.cancel_pending)

        self.suggestions=SuggestionsPanel(self.tabs,self)

        self.results=ttk.Frame(self.tabs,padding=12);self.tabs.add(self.results,text="Ordens e resultados")
        columns=("kind","id","symbol","side","qty","price","state","net")
        table_frame=ttk.Frame(self.results);table_frame.pack(fill="both",expand=True)
        self.table=ttk.Treeview(table_frame,columns=columns,show="headings")
        for col,title in zip(columns,("Tipo","Identificador","Ativo","Direção","Quantidade","Preço","Estado","Líquido")):
            self.table.heading(col,text=title);self.table.column(col,width=110,stretch=True)
        scrollbar=ttk.Scrollbar(table_frame,orient="vertical",command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left",fill="both",expand=True);scrollbar.pack(side="right",fill="y")
        self._button(self.results,"Exportar relatório JSON",self.export)
        self._button(self.results,"Backtest da série carregada",self.backtest)
        self._button(self.results,"Treinar modelo com CSV",self.train_model)

        settings=ttk.Frame(self.tabs,padding=12);self.tabs.add(settings,text="Risco e estratégias")
        settings_controls=ttk.Frame(settings);settings_controls.pack(fill='x')
        self._button(settings_controls,'Editar todos os parâmetros em formulários',self.open_settings,style='Accent.TButton')
        ttk.Label(settings,text="Valores na moeda da conta; risco por operação em fração (0.005 = 0,5%). Margens e custos são premissas de simulação.",wraplength=1000).pack(anchor="w",padx=8,pady=8)
        quick=ttk.LabelFrame(settings,text="Controles principais (PAPER)",padding=(12,8));quick.pack(fill="x",padx=8,pady=(0,10))
        self.quick_fields={
            "capital":("Capital",self.limits.capital),
            "risk_percent":("Risco por operação %",self.limits.risk_fraction*100),
            "daily_loss":("Perda máxima/dia",self.limits.daily_loss),
            "max_contracts":("Contratos máximos",self.limits.max_contracts),
            "max_trades":("Operações/dia",self.limits.max_trades),
            "strategy":("Estratégia",self.engine.strategy.name),
        }
        self.quick_vars={}
        for col,(key,(label,value)) in enumerate(self.quick_fields.items()):
            quick.columnconfigure(col,weight=1)
            ttk.Label(quick,text=label,style="Section.TLabel").grid(row=0,column=col,sticky="w",padx=4)
            var=tk.StringVar(value=str(value));self.quick_vars[key]=var
            if key=="strategy":
                widget=ttk.Combobox(quick,textvariable=var,values=("trend","breakout","pullback","adaptive","sma_cross","ema_pullback"),state="readonly",width=15)
            else:
                widget=ttk.Entry(quick,textvariable=var,width=17)
            widget.grid(row=1,column=col,sticky="ew",padx=4,pady=(5,8))
        ttk.Button(quick,text="Aplicar controles principais",style="Accent.TButton",
                   command=lambda:self.guard(self.apply_quick_settings)).grid(row=2,column=0,columnspan=3,sticky="w",padx=4)
        ttk.Label(settings,text="Configuração avançada: ativos, horários, custos, stops e calendário conferido pelo usuário em JSON.",style="Section.TLabel").pack(anchor="w",padx=8)
        self.settings_text=tk.Text(settings,height=15,font=("Consolas",11),wrap="none",padx=12,pady=10,relief="flat",highlightthickness=1)
        self.settings_text.pack(fill="both",expand=True,padx=8)
        self.settings_text.insert("1.0",json.dumps({"limits":asdict(self.limits),"execution":asdict(self.costs),"strategy":{"name":self.engine.strategy.name,"reward_r":self.engine.strategy.reward_r,"stop_atr":self.engine.strategy.stop_atr,"multi_timeframe":self.engine.strategy.multi_timeframe},"calendar":self.engine.calendar.to_config() if self.engine.calendar else None},indent=2))
        self._button(settings,"Validar e aplicar configuração",self.apply_settings,style="Accent.TButton")
        self._button(settings,"Liberar emergência local",lambda:self.emergency(False))

        about=ttk.Frame(self.tabs,padding=22);self.tabs.add(about,text="Conexões e ajuda")
        ttk.Label(about,text="RICO / PROFIT  •  DESCONECTADO",style="Section.TLabel").pack(anchor="w",pady=(0,10))
        help_text=("Esta versão apenas simula operações. Login no Home Broker não conecta o PULSE nem habilita ordens reais.\n\n"
                   "Para treinar: importe um CSV autorizado com symbol,ts,open,high,low,close,volume,source,seconds. "
                   "Os horários devem incluir fuso (ex.: 2026-01-05T12:00:00+00:00).\n\n"
                   "O replay não fornece cotações em tempo real. A emergência cancela entradas pendentes e bloqueia novas entradas; "
                   "os stops continuam ativos na simulação. Use Zerar posições PAPER para encerrar exposições simuladas.\n\n"
                   "Dados, posições e bloqueios ficam no SQLite local. Fechar o aplicativo pausa a simulação.")
        ttk.Label(about,text=help_text,style="Help.TLabel",justify="left",wraplength=960).pack(anchor="nw",fill="x")
        self._button(about,'Criar backup da pasta de dados',self.backup_data)
        self._button(about,'Restaurar backup em outra pasta',self.restore_data)
        self._button(about,'Abrir outra pasta de dados',self.open_data_directory)
        self._button(about,'Abrir memória de aprendizado',self.open_learning_memory)

    def open_learning_memory(self):
        import os
        from .learning import LearningMemory
        memory=LearningMemory(self.data_dir/'aprendizado')
        os.startfile(memory.directory)

    def open_settings(self):
        from .settings_ui import SettingsWindow
        return SettingsWindow(self)

    def backup_data(self):
        from .backups import create_backup
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.zip',initialfile='pulse-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip')
        if path:
            self.jobs.start(lambda:create_backup(self.data_dir,path),lambda result:self.status.set('Backup verificado: '+result['path']))

    def restore_data(self):
        from .backups import restore_backup
        path=filedialog.askopenfilename(parent=self.root,title='Backup PULSE',filetypes=[('ZIP','*.zip')])
        if not path:return
        directory=filedialog.askdirectory(parent=self.root,title='Escolha uma pasta vazia para restaurar')
        if directory:
            def done(result):
                self.status.set('Backup restaurado em '+result['directory'])
                if messagebox.askyesno('Backup restaurado','Abrir os dados restaurados agora? A pasta atual será preservada.',parent=self.root):
                    self.open_data_directory(result['directory'])
            self.jobs.start(lambda:restore_backup(path,directory),done)

    def open_data_directory(self,directory=None):
        import subprocess,sys
        directory=directory or filedialog.askdirectory(parent=self.root,title='Pasta dos dados PULSE')
        if not directory:return
        destination=Path(directory).resolve()
        command=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve().parents[2]/'main.py')]
        subprocess.Popen(command+['--data-dir',str(destination)],creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.close()

    def _theme(self):
        bg,fg,panel,raised,muted,border=(
            ("#0c1422","#edf3fc","#111e30","#19283b","#91a5bf","#30435d") if self.dark else
            ("#edf2f8","#17273d","#ffffff","#f7faff","#52667f","#cbd6e4"))
        accent="#438cff" if self.dark else "#175de0"
        self.root.configure(bg=bg)
        st=ttk.Style(self.root);st.theme_use("clam")
        st.configure(".",background=bg,foreground=fg,font=("Segoe UI",10))
        st.configure("TFrame",background=bg)
        st.configure("TLabel",background=bg,foreground=fg)
        st.configure("Brand.TLabel",font=("Segoe UI Semibold",19),foreground=accent)
        st.configure("BrandMuted.TLabel",font=("Segoe UI Semibold",19),foreground=fg)
        st.configure("Badge.TLabel",background=raised,foreground="#8fd9ff",font=("Segoe UI Semibold",10),padding=(12,6))
        st.configure("Status.TLabel",foreground=muted,font=("Segoe UI",10))
        st.configure("Section.TLabel",foreground=muted,font=("Segoe UI Semibold",9))
        st.configure("Metric.TFrame",background=panel,borderwidth=1,relief="solid")
        st.configure("MetricLabel.TLabel",background=panel,foreground=muted,font=("Segoe UI Semibold",9))
        st.configure("MetricValue.TLabel",background=panel,foreground=fg,font=("Segoe UI Semibold",13))
        st.configure("Signal.TLabel",background=raised,foreground=fg,font=("Segoe UI",10),padding=(12,9))
        st.configure("Help.TLabel",foreground=fg,font=("Segoe UI",11),padding=4)
        st.configure("TButton",background=raised,foreground=fg,bordercolor=border,lightcolor=raised,darkcolor=raised,
                     focuscolor=accent,relief="flat",padding=(12,8),font=("Segoe UI Semibold",10))
        st.map("TButton",background=[("pressed",border),("active",panel)],foreground=[("disabled",muted)])
        st.configure("Accent.TButton",background=accent,foreground="white",bordercolor=accent,lightcolor=accent,darkcolor=accent)
        st.map("Accent.TButton",background=[("pressed","#184caf"),("active","#3174d9")],foreground=[("active","white")])
        st.configure("Danger.TButton",background="#572b35" if self.dark else "#fff0f0",
                     foreground="#ffb5bf" if self.dark else "#aa2338",bordercolor="#b3485b",lightcolor=panel,darkcolor=panel)
        st.map("Danger.TButton",background=[("active","#713641" if self.dark else "#ffe0e4")])
        st.configure("TCombobox",padding=(7,7),fieldbackground=panel,background=raised,foreground=fg,arrowcolor=fg)
        st.map("TCombobox",fieldbackground=[("readonly",panel)],foreground=[("readonly",fg)])
        st.configure("TCheckbutton",background=bg,foreground=fg,padding=7)
        st.map("TCheckbutton",background=[("active",bg)],foreground=[("active",fg)])
        st.configure("TNotebook",background=bg,borderwidth=0)
        st.configure("TNotebook.Tab",background=bg,foreground=muted,padding=(17,10),borderwidth=0)
        st.map("TNotebook.Tab",background=[("selected",panel)],foreground=[("selected",accent)])
        st.configure("Treeview",background=panel,fieldbackground=panel,foreground=fg,rowheight=32,borderwidth=0)
        st.configure("Treeview.Heading",background=raised,foreground=muted,padding=8,font=("Segoe UI Semibold",10))
        st.map("Treeview",background=[("selected",accent)],foreground=[("selected","white")])
        self.chart.configure(bg=panel)
        self.settings_text.configure(bg=panel,fg=fg,insertbackground=fg,highlightbackground=border,highlightcolor=accent)
        self.suggestions.apply_theme(self.dark)
        self.draw()

    def toggle_theme(self):self.dark=not self.dark;self._theme()

    def _restore_feed(self):
        saved=self.ledger.read().get("feed")
        if saved and saved.get("kind")=="csv":
            path=Path(saved["path"])
            if not path.is_file(): self.status.set("CSV anterior indisponível. Posições preservadas; carregue o mesmo arquivo.");return
            provider=CSVProvider(path)
            if provider.sha256!=saved["sha256"]:raise ValueError("CSV changed; cannot resume existing exposure")
            self.feed=provider.bars();self.symbol.set(self.feed[0].symbol)
        else:
            self.symbol.set(saved.get("symbol","WIN") if saved else "WIN")
            self.feed=SyntheticProvider(self.symbol.get(),5000).bars()
        self._resume()

    def _resume(self):
        s=self.ledger.read();last=s["last_bars"].get(self.symbol.get())
        self.cursor=next((i for i,b in enumerate(self.feed) if not last or b.ts>=datetime.fromisoformat(last)),len(self.feed))
        self.bars=self.feed[max(0,self.cursor-1000):self.cursor]
        self.engine.history[self.symbol.get()]=self.bars.copy()
        self._configure_periods()
        self.status.set("PAPER | "+("Fonte: "+self.feed[0].source if self.feed else "Sem dados")+" | Replay local; corretora desconectada")

    def _configure_periods(self):
        base=self.feed[0].seconds if self.feed else 60
        available=[seconds for seconds in (60,300,900) if seconds>=base and seconds%base==0]
        if base not in available:available.insert(0,base)
        self._period_seconds={"Diário" if seconds==86400 else f"{seconds//60} min" if seconds%60==0 else f"{seconds} s":seconds
                              for seconds in available}
        self.period_combo.configure(values=tuple(self._period_seconds))
        if self.timeframe.get() not in self._period_seconds:
            self.timeframe.set(next(iter(self._period_seconds)))

    def _selected_seconds(self):
        base=self.bars[-1].seconds if self.bars else (self.feed[0].seconds if self.feed else 60)
        return max(base,self._period_seconds.get(self.timeframe.get(),base))

    def _can_load(self):
        self.pause();s=self.ledger.read()
        if s["positions"] or any(o["status"]=="NEW" for o in s["orders"].values()): raise ValueError("Pause e encerre posições/cancele ordens antes de trocar a série")

    def load_synthetic(self):
        self._can_load()
        self.feed=SyntheticProvider(self.symbol.get(),5000).bars()
        with self.ledger.transaction() as s:s["feed"]={"kind":"synthetic","symbol":self.symbol.get()}
        self._resume();self.refresh()

    def import_csv(self):
        self._can_load();path=filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
        if not path:return
        provider=CSVProvider(path);bars=provider.bars()
        if len({b.symbol for b in bars})!=1:raise ValueError("Selecione CSV de um único ativo")
        if bars[0].symbol not in self.engine.specs:raise ValueError("Instrumento desconhecido; configure a especificação primeiro")
        store=CandleStore(self.data_dir/"candles.sqlite")
        try:store.put(bars)
        finally:store.close()
        self.feed=bars;self.symbol.set(bars[0].symbol)
        with self.ledger.transaction() as s:s["feed"]={"kind":"csv","path":str(Path(path).resolve()),"sha256":provider.sha256}
        self._resume();self.refresh()

    def start(self):
        if self.running:return
        self.running=True;self._tick()
    def pause(self):
        self.running=False
        if self.timer:self.root.after_cancel(self.timer);self.timer=None
    def _tick(self):
        self.timer=None
        if self.running:
            self.guard(self.step)
            if self.running:self.timer=self.root.after(350,self._tick)
    def step(self):
        if self.cursor>=len(self.feed):self.pause();self.status.set("Fim da série PAPER. Exporte os resultados.");return
        b=self.feed[self.cursor]
        self.engine.on_bar(b,automatic=self.auto.get());self.cursor+=1
        self.bars.append(b);self.bars=self.bars[-1000:];self.offset=0
        self.refresh()
    def now(self):return self.bars[-1].ts+timedelta(seconds=self.bars[-1].seconds) if self.bars else datetime.now(UTC)
    def emergency(self,enabled):
        self.engine.emergency(self.now(),enabled);self.pause();self.refresh()
    def flatten(self):self.pause();self.engine.flatten(self.now());self.refresh()
    def cancel_pending(self):
        for key,o in self.ledger.read()["orders"].items():
            if o["status"]=="NEW":self.engine.cancel(key,self.now())
        self.refresh()
    def manual(self,side):
        if len(self.bars)<35:raise ValueError("Aguarde 35 candles para calcular ATR")
        from .indicators import snapshot
        b=self.bars[-1];a=snapshot(self.bars)["atr"]*self.engine.strategy.stop_atr;direction=1 if side=="BUY" else -1
        now=self.now();d=Decision(b.symbol,side,b.close,b.close-direction*a,b.close+direction*a*self.engine.strategy.reward_r,now,now+timedelta(seconds=b.seconds*3),self.engine.strategy.name,"manual / ATR / risco central")
        o=self.engine.submit(d);self.status.set("PAPER: "+o["status"]+" / "+o["message"]);self.refresh()
    def apply_settings(self):
        self.pause();data=json.loads(self.settings_text.get("1.0","end"))
        limits=Limits(**data["limits"]);costs=ExecutionSettings(**data["execution"]);strategy=Strategy(**data["strategy"])
        calendar=SessionCalendar.from_config(data["calendar"]) if data.get("calendar") is not None else None
        specs={key:Instrument(**value) for key,value in data['instruments'].items()} if data.get('instruments') else self.engine.specs
        engine=PaperEngine(self.ledger,limits,costs,instruments=specs,strategy=strategy,calendar=calendar);engine.history=self.engine.history
        self.engine=engine;self.limits=limits;self.costs=costs
        self.asset_combo.configure(values=list(engine.specs))
        self.suggestions.signature=None
        self.suggestions.analyze()
        for key,value in (("capital",limits.capital),("risk_percent",limits.risk_fraction*100),
                          ("daily_loss",limits.daily_loss),("max_contracts",limits.max_contracts),
                          ("max_trades",limits.max_trades),("strategy",strategy.name)):
            self.quick_vars[key].set(str(value))
        self.status.set("Configuração validada e salva. Execução: PAPER.");self.refresh()
    def apply_quick_settings(self):
        data=json.loads(self.settings_text.get("1.0","end"))
        get=lambda key: self.quick_vars[key].get().strip().replace(",",".")
        data["limits"].update(capital=float(get("capital")),risk_fraction=float(get("risk_percent"))/100,
                              daily_loss=float(get("daily_loss")),max_contracts=int(get("max_contracts")),
                              max_trades=int(get("max_trades")))
        data["strategy"]["name"]=get("strategy")
        # Commit the visible advanced text only after all values pass validation.
        Limits(**data["limits"]).validate();ExecutionSettings(**data["execution"]).validate()
        Strategy(**data["strategy"])
        current=self.settings_text.get("1.0","end")
        self.settings_text.delete("1.0","end")
        self.settings_text.insert("1.0",json.dumps(data,indent=2,ensure_ascii=False))
        try:self.apply_settings()
        except Exception:
            self.settings_text.delete("1.0","end");self.settings_text.insert("1.0",current)
            raise
    def export(self):
        path=filedialog.asksaveasfilename(defaultextension=".json",initialfile="pulse-paper.json")
        if path:
            s=self.ledger.read();save_report({"mode":"PAPER","sources":s["last_sources"],"metrics":metrics(s["trades"],self.limits.capital),"state":s},path)
            self.status.set("Relatório PAPER exportado: "+path)
    def backtest(self):
        if not self.feed:raise ValueError("Carregue dados")
        self.pause();path=filedialog.asksaveasfilename(defaultextension=".json",initialfile="pulse-backtest.json")
        if path:
            # Separate ledger; never modifies the current paper positions.
            bars=list(self.feed);strategy=self.engine.strategy;limits=self.limits;costs=self.costs;calendar=self.engine.calendar;specs=dict(self.engine.specs)
            def done(report):
                save_report(report,path)
                self.status.set("Backtest concluído / "+str(report["metrics"]["trades"])+" operações / "+path)
            self.jobs.start(lambda:run_backtest(bars,strategy,limits,costs,calendar=calendar,instruments=specs),done)
            self.status.set('Backtest em segundo plano; a interface continua disponível…')
    def train_model(self):
        if not self.feed or self.ledger.read().get("feed",{}).get("kind")!="csv":
            raise ValueError("Importe um CSV histórico autorizado antes de treinar o modelo")
        if len(self.feed)<200:raise ValueError("O treinamento precisa de pelo menos 200 candles de um único ativo")
        self.pause()
        path=filedialog.asksaveasfilename(defaultextension=".json",initialfile="pulse-modelo-paper.json")
        if path:
            from .ml import train_temporal
            bars=list(self.feed)
            def done(report):
                from .learning import LearningMemory
                LearningMemory(self.data_dir/'aprendizado').remember_model(bars,report,path)
                self.status.set(f"Modelo PAPER salvo. Acerto validação: {report['validation']['accuracy']:.1%}; "
                            f"referência: {report['validation']['majority_accuracy']:.1%}. "
                            "Modelo sem permissão de executar ordens.")
            self.jobs.start(lambda:train_temporal(bars,path,feature_set='regime_flow_v2'),done)
            self.status.set('Treinamento em segundo plano…')
    def refresh(self):
        s=self.ledger.read();m=metrics(s["trades"],self.limits.capital)
        pnl,unrealized,worst=self.engine.risk.period_pnl(s,self.now())
        self.summary.set(f"Moeda {self.limits.currency} | Capital {self.limits.capital:,.2f} | Dia {pnl['day']+unrealized:,.2f} | Risco aberto {worst:,.2f} | Posições {len(s['positions'])} | Trades {m['trades']} | Win rate {m['win_rate']:.0%} | Emergência {'ATIVA' if s['emergency'] else 'não'}")
        self.metrics["capital"].set(self._brl(self.limits.capital))
        self.metrics["day"].set(self._brl(pnl['day']+unrealized))
        self.metrics["exposure"].set(self._brl(worst))
        self.metrics["positions"].set(str(len(s["positions"])))
        self.metrics["trades"].set(str(m["trades"]))
        self.metrics["emergency"].set("BLOQUEADA" if s["emergency"] else "PAPER ATIVO")
        d=self.engine.last_decision
        if d:self.signal_text.set(f"{d.symbol} {d.side} | Entrada {d.price:.2f} / Stop {d.stop:.2f} / Alvo {d.target:.2f} / R:R {d.rr:.2f} | {d.reason}\nConfiança calibrada: indisponível. Válido até {d.expires.isoformat()}")
        self.table.delete(*self.table.get_children())
        for o in list(s["orders"].values())[-100:]:self.table.insert("","end",values=("Ordem",o["id"][:10],o["symbol"],o["side"],o["filled_qty"] or o["qty"],round(o.get("filled_price",o["price"]),2),o["status"]+" / "+o["message"],""))
        for p in s["positions"].values():self.table.insert("","end",values=("Posição",p["id"][:10],p["symbol"],p["side"],p["qty"],round(p["entry"],2),"ABERTA",""))
        for t in s["trades"][-100:]:self.table.insert("","end",values=("Resultado",t["id"][:10],t["symbol"],t["side"],t["qty"],round(t["exit"],2),t["exit_reason"],round(t["net"],2)))
        self.suggestions.replay_changed()
        self.draw()
    def zoom(self,factor):self.window=max(15,min(300,int(self.window*factor)));self.draw()
    def change_period(self):self.offset=0;self.draw()
    def pan(self,delta):
        count=len(aggregate(self.bars,self._selected_seconds())) if self.bars else 0
        self.offset=max(0,min(max(0,count-self.window),self.offset+delta))
        self.draw()
    @staticmethod
    def _ema_series(values,period):
        result=[None]*len(values)
        if len(values)<period:return result
        average=mean(values[:period]);result[period-1]=average
        multiplier=2/(period+1)
        for index in range(period,len(values)):
            average+=multiplier*(values[index]-average)
            result[index]=average
        return result

    def _brl(self,value):
        return ('R$' if self.limits.currency=='BRL' else self.limits.currency)+' '+f"{value:,.2f}".replace(",","_").replace(".",",").replace("_",".")

    def draw(self):
        if not hasattr(self,"chart"):return
        c=self.chart;c.delete("all");self._chart_image=None
        w=max(c.winfo_width(),280);h=max(c.winfo_height(),210)
        fg="#9cb0c9" if self.dark else "#53677e"
        grid="#2b3b50" if self.dark else "#dce4ee"
        up="#48c5b1" if self.dark else "#118875"
        down="#f47787" if self.dark else "#cc5369"
        c.create_text(26,18,anchor="w",fill=fg,text="PAPER  •  HORÁRIO DE BRASÍLIA  •  DADOS SIMULADOS OU CSV",font=("Segoe UI Semibold",10))
        selected=self._selected_seconds()
        all_rows=aggregate(self.bars,selected) if self.bars else []
        self.offset=min(self.offset,max(0,len(all_rows)-self.window))
        end=max(0,len(all_rows)-self.offset)
        start=max(0,end-self.window)
        rows=all_rows[start:end]
        if not rows:
            c.create_text(w/2,h/2,text="Inicie o replay ou importe um CSV para visualizar o mercado",fill=fg,font=("Segoe UI",11))
            return

        lo=min(b.low for b in rows);hi=max(b.high for b in rows)
        span=max(hi-lo,.01);lo-=span*.12;hi+=span*.12
        left,right,top,bottom=26,max(160,w-100),38,max(110,h*.72)
        volume_base=h-35;volume_height=max(18,volume_base-bottom-28)
        def y(value):return bottom-(value-lo)/(hi-lo)*(bottom-top)
        step=(right-left)/len(rows)
        candle_width=max(1.6,min(step*.65,13))
        for i in range(5):
            value=lo+(hi-lo)*i/4;yy=y(value)
            c.create_line(left,yy,right,yy,fill=grid)
            c.create_text(right+9,yy,text=f"{value:,.2f}",anchor="w",fill=fg,font=("Consolas",9))
        c.create_line(left,bottom+13,right,bottom+13,fill=grid)
        c.create_text(left,bottom+25,text="VOLUME",anchor="w",fill=fg,font=("Segoe UI Semibold",8))
        maxvol=max(b.volume for b in rows) or 1
        closes=[b.close for b in all_rows]
        curves=[]
        for period,color in ((9,"#ffd27b"),(21,"#a9a1ff")):
            series=self._ema_series(closes,period)[start:end]
            points=[(left+(i+.5)*step,y(value)) for i,value in enumerate(series) if value is not None]
            curves.append((points,color))

        # Tk Canvas is crisp for labels, but has no antialiasing for diagonal
        # lines. Pillow renders the market layer at 2x and downsamples it.
        if Image is not None:
            factor=2
            layer=Image.new("RGBA",(w*factor,h*factor),(0,0,0,0))
            pen=ImageDraw.Draw(layer)
            def point(x,y0):return (round(x*factor),round(y0*factor))
            for i,b in enumerate(rows):
                x=left+(i+.5)*step;color=up if b.close>=b.open else down
                pen.rectangle((*point(x-candle_width/2,volume_base-b.volume/maxvol*volume_height),
                               *point(x+candle_width/2,volume_base)),fill=color)
                pen.line((point(x,y(b.high)),point(x,y(b.low))),fill=color,width=factor)
                upper=y(max(b.open,b.close));lower=max(y(min(b.open,b.close)),upper+1)
                pen.rectangle((*point(x-candle_width/2,upper),*point(x+candle_width/2,lower)),fill=color)
            for points,color in curves:
                if len(points)>1:pen.line([point(x,y0) for x,y0 in points],fill=color,width=round(2.2*factor),joint="curve")
            self._chart_image=ImageTk.PhotoImage(layer.resize((w,h),Image.Resampling.LANCZOS),master=c)
            c.create_image(0,0,anchor="nw",image=self._chart_image)
        else:
            for i,b in enumerate(rows):
                x=left+(i+.5)*step;color=up if b.close>=b.open else down
                c.create_rectangle(x-candle_width/2,volume_base-b.volume/maxvol*volume_height,
                                   x+candle_width/2,volume_base,fill=color,outline="")
                c.create_line(x,y(b.high),x,y(b.low),fill=color,width=1.3)
                upper=y(max(b.open,b.close));lower=max(y(min(b.open,b.close)),upper+1)
                c.create_rectangle(x-candle_width/2,upper,x+candle_width/2,lower,fill=color,outline=color)
            if any(len(points)>1 for points,_ in curves):
                self._chart_image=tk.PhotoImage(data=antialiased_lines_png(w,h,curves),format="png",master=c)
                c.create_image(0,0,anchor="nw",image=self._chart_image)

        for p in self.ledger.read()["positions"].values():
            if p["symbol"]!=rows[-1].symbol:continue
            for key,label,color in (("entry","ENTRADA",up),("stop","STOP",down),("target","ALVO","#a9a1ff")):
                yy=y(p[key])
                if top<=yy<=bottom:
                    c.create_line(left,yy,right,yy,fill=color,dash=(4,4))
                    c.create_text(left+6,yy-9,text=f"{label}  {p[key]:,.2f}",fill=color,anchor="w",font=("Segoe UI Semibold",9))
        for i in range(5):
            index=min(len(rows)-1,round(i*(len(rows)-1)/4))
            x=left+(index+.5)*step
            c.create_text(x,h-11,text=local_time(rows[index].ts).strftime("%d/%m %H:%M"),fill=fg,
                          anchor="w" if i==0 else "e" if i==4 else "center",font=("Segoe UI",9))
        c.create_text(right-10,18,anchor="e",fill="#ffd27b",text="EMA 9",font=("Segoe UI Semibold",9))
        c.create_text(right-82,18,anchor="e",fill="#a9a1ff",text="EMA 21",font=("Segoe UI Semibold",9))

    def close(self):
        self.pause();self.suggestions.data_center.close();self.jobs.close();self.ledger.close();self.root.destroy()
    def run(self):self.root.mainloop()

def launch_dashboard():Dashboard().run()
