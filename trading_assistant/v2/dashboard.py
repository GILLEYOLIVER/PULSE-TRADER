from __future__ import annotations
import json
import os
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from datetime import datetime,timedelta
from pathlib import Path
from dataclasses import asdict,fields
from .models import Limits,ExecutionSettings,Decision,INSTRUMENTS,UTC
from .data import SyntheticProvider,CSVProvider,aggregate,CandleStore
from .execution import PaperEngine
from .ledger import Ledger
from .strategy import Strategy
from .backtest import metrics,run_backtest,save_report

class Dashboard:
    def __init__(self,data_dir=None):
        try:
            import customtkinter as ctk
            ctk.set_appearance_mode("dark");self.root=ctk.CTk()
        except ImportError:
            self.root=tk.Tk()
        self.root.title("PULSE-TRADER 2.0 | PAPER")
        self.root.geometry("1280x820");self.root.minsize(950,650)
        self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.data_dir=Path(data_dir or os.getenv("PULSE_DATA_DIR","runtime"));self.data_dir.mkdir(parents=True,exist_ok=True)
        self.ledger=Ledger(self.data_dir/"paper.sqlite")
        config=self.ledger.read().get("config",{})
        self.limits=Limits(**config.get("limits",{}));self.costs=ExecutionSettings(**config.get("costs",{}))
        self.engine=PaperEngine(self.ledger,self.limits,self.costs,strategy=Strategy(**config.get("strategy",{})))
        self.bars=[];self.feed=[];self.cursor=0;self.running=False;self.timer=None
        self.window=70;self.offset=0;self.dark=True
        self.symbol=tk.StringVar(value="WIN");self.strategy=tk.StringVar(value="trend")
        self.timeframe=tk.StringVar(value="60");self.auto=tk.BooleanVar(value=True)
        self.status=tk.StringVar(value="PAPER | Fonte: SYNTHETIC | Sem conexão com corretora")
        self.summary=tk.StringVar();self.signal_text=tk.StringVar(value="Aguardando 35 candles fechados. Confiança estatística: indisponível.")
        self._build();self._theme();self._restore_feed();self.refresh()

    def _button(self,parent,text,command):
        b=ttk.Button(parent,text=text,command=lambda:self.guard(command));b.pack(side="left",padx=4,pady=5);return b

    def guard(self,fn):
        try:return fn()
        except Exception as e:
            self.pause();self.status.set("BLOQUEADO: "+str(e));messagebox.showerror("PULSE-TRADER",str(e),parent=self.root)

    def _build(self):
        top=ttk.Frame(self.root,padding=12);top.pack(fill="x")
        ttk.Label(top,text="PULSE / TRADER",font=("Segoe UI",20,"bold")).pack(side="left")
        ttk.Label(top,text="  2.0   •   SOMENTE PAPER",font=("Segoe UI",11,"bold")).pack(side="left")
        self._button(top,"Tema claro/escuro",self.toggle_theme)
        ttk.Label(self.root,textvariable=self.status,font=("Segoe UI",11)).pack(anchor="w",padx=16)
        ttk.Label(self.root,textvariable=self.summary,font=("Segoe UI",12,"bold")).pack(anchor="w",padx=16,pady=10)
        toolbar=ttk.Frame(self.root);toolbar.pack(fill="x",padx=10)
        ttk.Label(toolbar,text="Ativo").pack(side="left")
        ttk.Combobox(toolbar,textvariable=self.symbol,values=list(INSTRUMENTS),width=9,state="readonly").pack(side="left",padx=4)
        self._button(toolbar,"Carregar simulação",self.load_synthetic)
        self._button(toolbar,"Importar CSV",self.import_csv)
        self._button(toolbar,"Iniciar",self.start);self._button(toolbar,"Pausar",self.pause)
        self._button(toolbar,"Próximo candle",self.step)
        ttk.Checkbutton(toolbar,text="Paper automático",variable=self.auto).pack(side="left",padx=6)
        self._button(toolbar,"EMERGÊNCIA",lambda:self.emergency(True))
        self.tabs=ttk.Notebook(self.root);self.tabs.pack(fill="both",expand=True,padx=12,pady=10)
        charttab=ttk.Frame(self.tabs);self.tabs.add(charttab,text="Mercado e sinais")
        controls=ttk.Frame(charttab);controls.pack(fill="x")
        self._button(controls,"Zoom +",lambda:self.zoom(.75));self._button(controls,"Zoom −",lambda:self.zoom(1.3))
        self._button(controls,"←",lambda:self.pan(20));self._button(controls,"→",lambda:self.pan(-20))
        ttk.Label(controls,text="Gráfico (segundos)").pack(side="left",padx=4)
        combo=ttk.Combobox(controls,textvariable=self.timeframe,values=("60","300","900"),width=8,state="readonly");combo.pack(side="left");combo.bind("<<ComboboxSelected>>",lambda _:self.draw())
        self.chart=tk.Canvas(charttab,highlightthickness=0,height=330);self.chart.pack(fill="both",expand=True,pady=8)
        self.chart.bind("<Configure>",lambda _:self.draw())
        self.chart.bind("<MouseWheel>",lambda e:self.zoom(.85 if e.delta>0 else 1.2))
        ttk.Label(charttab,textvariable=self.signal_text,wraplength=1100).pack(fill="x",pady=8)
        manual=ttk.Frame(charttab);manual.pack(fill="x")
        self._button(manual,"Compra PAPER por risco",lambda:self.manual("BUY"))
        self._button(manual,"Venda PAPER por risco",lambda:self.manual("SELL"))
        self._button(manual,"Zerar posições PAPER",self.flatten)
        self._button(manual,"Cancelar ordens pendentes",self.cancel_pending)
        self.results=ttk.Frame(self.tabs);self.tabs.add(self.results,text="Ordens, posições e resultados")
        columns=("kind","id","symbol","side","qty","price","state","net")
        self.table=ttk.Treeview(self.results,columns=columns,show="headings")
        for col,title in zip(columns,("Tipo","Identificador","Ativo","Direção","Quantidade","Preço","Estado","Líquido R$")):
            self.table.heading(col,text=title);self.table.column(col,width=110,stretch=True)
        self.table.pack(fill="both",expand=True)
        self._button(self.results,"Exportar relatório JSON",self.export)
        self._button(self.results,"Backtest da série carregada",self.backtest)
        settings=ttk.Frame(self.tabs);self.tabs.add(settings,text="Risco, custos e estratégias")
        ttk.Label(settings,text="Valores em R$; risco por operação em fração (0.005 = 0,5%). Margens e custos são premissas de simulação.").pack(anchor="w",padx=8,pady=8)
        self.settings_text=tk.Text(settings,height=15,font=("Consolas",10),wrap="none")
        self.settings_text.pack(fill="both",expand=True,padx=8)
        self.settings_text.insert("1.0",json.dumps({"limits":asdict(self.limits),"execution":asdict(self.costs),"strategy":{"name":self.engine.strategy.name,"reward_r":self.engine.strategy.reward_r,"stop_atr":self.engine.strategy.stop_atr,"multi_timeframe":self.engine.strategy.multi_timeframe}},indent=2))
        self._button(settings,"Validar e aplicar configuração",self.apply_settings)
        self._button(settings,"Liberar emergência local",lambda:self.emergency(False))
        about=ttk.Frame(self.tabs,padding=18);self.tabs.add(about,text="Conexões e ajuda")
        ttk.Label(about,text="Rico / Profit: NÃO CONECTADO\nExecução REAL: indisponível nesta versão\n\nCSV: symbol,ts,open,high,low,close,volume,source,seconds\nUse timestamp ISO 8601 com fuso (ex.: 2026-01-05T12:00:00+00:00).\n\nO replay e a simulação avançam pelo relógio dos candles. Não são cotações em tempo real.\nOrdens são enviadas à abertura do próximo candle; stops são conservadores.\nA emergência cancela entradas pendentes e bloqueia novas entradas. Stops continuam ativos.\nUse Zerar posições PAPER para encerrar posições existentes.\n\nModelos opcionais e walk-forward: python -m trading_assistant.v2.cli --help\nDados, posições, limites e bloqueios são persistidos em SQLite.\nFechar o aplicativo pausa a simulação; não há proteção de corretora nem dinheiro real.",font=("Segoe UI",12),justify="left",wraplength=1000).pack(anchor="nw")

    def _theme(self):
        bg,fg,panel=("#101722","#e5edf7","#192535") if self.dark else ("#edf2f8","#15233a","#ffffff")
        self.root.configure(bg=bg)
        st=ttk.Style(self.root);st.theme_use("clam")
        st.configure(".",background=bg,foreground=fg,font=("Segoe UI",10))
        st.configure("TButton",background=panel,padding=7)
        st.configure("TNotebook.Tab",background=panel,padding=(14,8))
        st.map("TNotebook.Tab",background=[("selected","#2463eb")],foreground=[("selected","white")])
        st.configure("Treeview",background=panel,fieldbackground=panel,foreground=fg,rowheight=28)
        self.chart.configure(bg=panel);self.settings_text.configure(bg=panel,fg=fg,insertbackground=fg)
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
        self.status.set("PAPER | "+("Fonte: "+self.feed[0].source if self.feed else "Sem dados")+" | Replay local; corretora desconectada")

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
        engine=PaperEngine(self.ledger,limits,costs,strategy=strategy);engine.history=self.engine.history
        self.engine=engine;self.limits=limits;self.costs=costs
        self.status.set("Configuração validada e salva. Execução: PAPER.");self.refresh()
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
            report=run_backtest(self.feed,self.engine.strategy,self.limits,self.costs);save_report(report,path)
            self.status.set("Backtest concluído / "+str(report["metrics"]["trades"])+" operações / "+path)
    def refresh(self):
        s=self.ledger.read();m=metrics(s["trades"],self.limits.capital)
        pnl,unrealized,worst=self.engine.risk.period_pnl(s,self.now())
        self.summary.set(f"Capital R$ {self.limits.capital:,.2f}   |   Dia R$ {pnl['day']+unrealized:,.2f}   |   Risco aberto R$ {worst:,.2f}   |   Posições {len(s['positions'])}   |   Trades {m['trades']}   |   Win rate {m['win_rate']:.0%}   |   Emergência {'ATIVA' if s['emergency'] else 'não'}")
        d=self.engine.last_decision
        if d:self.signal_text.set(f"{d.symbol} {d.side} | Entrada {d.price:.2f} / Stop {d.stop:.2f} / Alvo {d.target:.2f} / R:R {d.rr:.2f} | {d.reason}\nConfiança calibrada: indisponível. Válido até {d.expires.isoformat()}")
        self.table.delete(*self.table.get_children())
        for o in list(s["orders"].values())[-100:]:self.table.insert("","end",values=("Ordem",o["id"][:10],o["symbol"],o["side"],o["filled_qty"] or o["qty"],round(o.get("filled_price",o["price"]),2),o["status"]+" / "+o["message"],""))
        for p in s["positions"].values():self.table.insert("","end",values=("Posição",p["id"][:10],p["symbol"],p["side"],p["qty"],round(p["entry"],2),"ABERTA",""))
        for t in s["trades"][-100:]:self.table.insert("","end",values=("Resultado",t["id"][:10],t["symbol"],t["side"],t["qty"],round(t["exit"],2),t["exit_reason"],round(t["net"],2)))
        self.draw()
    def zoom(self,factor):self.window=max(15,min(300,int(self.window*factor)));self.draw()
    def pan(self,delta):self.offset=max(0,min(max(0,len(self.bars)-self.window),self.offset+delta));self.draw()
    def draw(self):
        if not hasattr(self,"chart"):return
        c=self.chart;c.delete("all");w=max(c.winfo_width(),200);h=max(c.winfo_height(),200)
        fg="#c4d2e8" if self.dark else "#24334a"
        c.create_text(16,16,anchor="w",fill=fg,text="PAPER • Dados sintéticos ou históricos • EMA9 / EMA21 • Volume",font=("Segoe UI",10))
        base=self.bars[-1].seconds if self.bars else 60
        selected=max(base,int(self.timeframe.get()));selected=((selected+base-1)//base)*base
        rows=aggregate(self.bars,selected) if self.bars else []
        end=max(0,len(rows)-self.offset);rows=rows[max(0,end-self.window):end]
        if not rows:c.create_text(w/2,h/2,text="Inicie a simulação ou importe um CSV",fill=fg);return
        lo=min(b.low for b in rows);hi=max(b.high for b in rows);span=max(hi-lo,.01);lo-=span*.1;hi+=span*.1
        left,right,top,bottom=20,w-90,45,h*.76
        def y(value):return bottom-(value-lo)/(hi-lo)*(bottom-top)
        step=(right-left)/len(rows);width=max(1,min(step*.65,12))
        for i in range(5):
            value=lo+(hi-lo)*i/4;yy=y(value);c.create_line(left,yy,right,yy,fill="#344258" if self.dark else "#d3dce8");c.create_text(right+7,yy,text=f"{value:.2f}",anchor="w",fill=fg)
        maxvol=max(b.volume for b in rows) or 1
        for i,b in enumerate(rows):
            x=left+(i+.5)*step;color="#4ab6ec" if b.close>=b.open else "#ed7185"
            c.create_line(x,y(b.high),x,y(b.low),fill=color)
            c.create_rectangle(x-width/2,y(max(b.open,b.close)),x+width/2,max(y(min(b.open,b.close)),y(max(b.open,b.close))+1),fill=color,outline=color)
            c.create_rectangle(x-width/2,h-24-b.volume/maxvol*(h-bottom-35),x+width/2,h-24,fill=color,outline="")
        from .indicators import ema
        closes=[b.close for b in rows]
        for period,color in ((9,"#f9ba52"),(21,"#ac91ff")):
            points=[]
            for i in range(period-1,len(rows)):points.extend((left+(i+.5)*step,y(ema(closes[:i+1],period))))
            if len(points)>=4:c.create_line(*points,fill=color,width=2)
        for p in self.ledger.read()["positions"].values():
            if p["symbol"]!=rows[-1].symbol:continue
            for key,color in (("entry","#4ab6ec"),("stop","#ed7185"),("target","#b9a2ff")):
                yy=y(p[key])
                if top<=yy<=bottom:c.create_line(left,yy,right,yy,fill=color,dash=(4,3));c.create_text(left+6,yy-8,text=key+" "+str(round(p[key],2)),fill=color,anchor="w")
        c.create_text(left,h-10,text=rows[0].ts.strftime("%d/%m %H:%M"),fill=fg,anchor="w")
        c.create_text(right,h-10,text=rows[-1].ts.strftime("%d/%m %H:%M"),fill=fg,anchor="e")
    def close(self):self.pause();self.ledger.close();self.root.destroy()
    def run(self):self.root.mainloop()

def launch_dashboard():Dashboard().run()
