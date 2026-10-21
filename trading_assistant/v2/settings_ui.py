"""Forms for every persisted risk/execution setting; no JSON editing required."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from dataclasses import asdict


LIMIT_LABELS={
 'capital':'Capital de referência na moeda da conta', 'risk_fraction':'Risco por operação %', 'daily_loss':'Perda máxima diária',
 'weekly_loss':'Perda máxima semanal', 'monthly_loss':'Perda máxima mensal', 'daily_target':'Meta diária',
 'max_positions':'Posições simultâneas', 'max_contracts':'Unidades/contratos máximos por ativo', 'max_trades':'Operações por dia',
 'max_spread_ticks':'Spread máximo em ticks', 'max_slippage_ticks':'Slippage máximo em ticks', 'max_exposure':'Exposição máxima na moeda da conta',
 'currency':'Moeda da conta: BRL, USD ou USDT','min_net_reward_r':'Alvo/risco mínimo após custos (0 desliga)',
 'consecutive_losses':'Perdas consecutivas para bloqueio', 'cooldown_seconds':'Bloqueio após perdas (segundos)',
 'start_hour':'Hora inicial (Brasília)', 'end_hour':'Hora final (Brasília)', 'allowed_symbols':'Ativos permitidos, separados por vírgula',
 'allowed_strategies':'Permitidas: trend, breakout, pullback, adaptive, sma_cross, ema_pullback, mean_reversion', 'max_data_age_seconds':'Idade máxima dos dados (segundos)'}
COST_LABELS={'spread_ticks':'Spread simulado em ticks','slippage_ticks':'Slippage simulado em ticks',
 'fee_per_unit':'Taxa fixa por unidade/lado na moeda da conta','fee_bps':'Taxa sobre o financeiro por lado (10 bps = 0,1%)','participation':'Participação máxima no volume (fração)',
 'latency_bars':'Latência em candles','trailing_atr':'Trailing em ATR (0 desliga)','break_even_r':'Break-even em R (0 desliga)'}


class SettingsWindow:
    def __init__(self,dashboard):
        self.dashboard=dashboard
        self.window=tk.Toplevel(dashboard.root);self.window.title('Todos os parâmetros PAPER');self.window.geometry('850x640')
        self.values={}
        engine=dashboard.engine
        self.config={'limits':asdict(engine.limits),'execution':asdict(engine.costs),'strategy':asdict(engine.strategy),
                     'instruments':{key:asdict(spec) for key,spec in engine.specs.items()},
                     'calendar':engine.calendar.to_config() if engine.calendar else None}
        ttk.Label(self.window,padding=12,wraplength=800,text='Configurações de simulação. Margens e taxas são premissas do usuário; confira o ativo e os custos. Alterações de configuração com exposição aberta são bloqueadas.').pack(fill='x')
        footer=ttk.Frame(self.window,padding=10);footer.pack(side='bottom',fill='x')
        ttk.Button(footer,text='Validar e salvar todos os parâmetros',command=lambda:dashboard.guard(self.apply)).pack(side='left')
        tabs=ttk.Notebook(self.window);tabs.pack(fill='both',expand=True,padx=12,pady=6)
        self.tabs=tabs
        for section,labels,title in (('limits',LIMIT_LABELS,'Risco'),('execution',COST_LABELS,'Execução')):
            form=self._scroll_tab(title)
            for row,(key,label) in enumerate(labels.items()):
                value=self.config[section][key]
                if key=='risk_fraction':value*=100
                if isinstance(value,(list,tuple)):value=', '.join(value)
                var=tk.StringVar(value=str(value));self.values[(section,key)]=var
                ttk.Label(form,text=label,wraplength=480).grid(row=row,column=0,sticky='w',padx=8,pady=5)
                ttk.Entry(form,textvariable=var,width=24).grid(row=row,column=1,sticky='ew',padx=8,pady=5)
            form.columnconfigure(1,weight=1)
        form=self._scroll_tab('Estratégia e sessão')
        for row,(key,label) in enumerate((('name','Estratégia'),('reward_r','Alvo em múltiplos do risco'),('stop_atr','Stop em múltiplos do ATR'))):
            var=tk.StringVar(value=str(self.config['strategy'][key]));self.values[('strategy',key)]=var
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',padx=8,pady=6)
            widget=ttk.Combobox(form,textvariable=var,values=('trend','breakout','pullback','adaptive','sma_cross','ema_pullback','mean_reversion'),state='readonly') if key=='name' else ttk.Entry(form,textvariable=var)
            widget.grid(row=row,column=1,padx=8,pady=6)
        self.multitimeframe=tk.BooleanVar(value=engine.strategy.multi_timeframe)
        ttk.Checkbutton(form,text='Exigir confirmação em período maior',variable=self.multitimeframe).grid(row=3,column=0,columnspan=2,sticky='w',padx=8,pady=6)
        self.calendar_enabled=tk.BooleanVar(value=engine.calendar is not None)
        self.calendar_verified=tk.BooleanVar(value=bool(engine.calendar and engine.calendar.verified))
        ttk.Checkbutton(form,text='Usar calendário de sessão informado pelo usuário',variable=self.calendar_enabled).grid(row=4,column=0,columnspan=2,sticky='w',padx=8,pady=6)
        calendar=self.config['calendar'] or {'start':'09:00:00','end':'18:00:00','holidays':[]}
        for row,(key,label) in enumerate((('start','Início HH:MM'),('end','Fim HH:MM'),('holidays','Feriados AAAA-MM-DD, separados por vírgula')),5):
            var=tk.StringVar(value=', '.join(calendar[key]) if key=='holidays' else calendar[key]);self.values[('calendar',key)]=var
            ttk.Label(form,text=label,wraplength=450).grid(row=row,column=0,sticky='w',padx=8,pady=6)
            ttk.Entry(form,textvariable=var,width=35).grid(row=row,column=1,padx=8,pady=6)
        ttk.Checkbutton(form,text='Conferi estes horários e feriados na fonte correspondente',variable=self.calendar_verified).grid(row=8,column=0,columnspan=2,sticky='w',padx=8,pady=8)
        form=self._scroll_tab('Especificações dos ativos')
        ttk.Label(form,text='Ticker (selecione ou digite um novo)').grid(row=0,column=0,padx=8,pady=8,sticky='w')
        self.instrument=tk.StringVar(value=next(iter(engine.specs)))
        combo=ttk.Combobox(form,textvariable=self.instrument,values=tuple(engine.specs));combo.grid(row=0,column=1,padx=8,pady=8)
        self.instrument_vars={}
        for row,(key,label) in enumerate((('point_value','Valor por ponto na moeda do ativo'),('tick','Variação mínima do preço'),('lot','Lote em unidades inteiras do motor'),('margin','Capital reservado por unidade'),('expiry','Vencimento AAAA-MM-DD (opcional)'),('currency','Moeda do ativo: BRL, USD ou USDT'),('volume_per_unit','Volume base correspondente a uma unidade do motor')),1):
            var=tk.StringVar();self.instrument_vars[key]=var
            ttk.Label(form,text=label,wraplength=450).grid(row=row,column=0,sticky='w',padx=8,pady=6)
            ttk.Entry(form,textvariable=var).grid(row=row,column=1,padx=8,pady=6)
        combo.bind('<<ComboboxSelected>>',lambda _:self.load_instrument())
        self.allow_short=tk.BooleanVar()
        ttk.Checkbutton(form,text='Permitir posição vendida simulada neste ativo',variable=self.allow_short).grid(row=8,column=0,columnspan=2,padx=8,pady=6,sticky='w')
        ttk.Label(form,text='BTC/ETH são BRL; BTCUSDT/ETHUSDT são USDT. Um ativo só opera se a moeda coincidir com a conta. Unidades menores exigem valor por ponto e volume por unidade compatíveis. Margens/taxas são premissas de simulação.',wraplength=700).grid(row=9,column=0,columnspan=2,padx=8,pady=12)
        self.load_instrument()

    def _scroll_tab(self,title):
        tab=ttk.Frame(self.tabs);self.tabs.add(tab,text=title)
        canvas=tk.Canvas(tab,highlightthickness=0)
        scroll=ttk.Scrollbar(tab,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
        form=ttk.Frame(canvas,padding=8);item=canvas.create_window(0,0,window=form,anchor='nw')
        form.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(item,width=event.width))
        canvas.bind('<MouseWheel>',lambda event:canvas.yview_scroll(-1 if event.delta>0 else 1,'units'))
        return form

    def load_instrument(self):
        spec=self.config['instruments'].get(self.instrument.get())
        if spec:
            for key,var in self.instrument_vars.items():var.set('' if spec[key] is None else str(spec[key]))
            self.allow_short.set(spec['allow_short'])

    def apply(self):
        import re
        from .models import Instrument
        data=json.loads(json.dumps(self.config))
        for (section,key),var in self.values.items():
            if section=='calendar':continue
            value=var.get().strip()
            old=data[section][key]
            if isinstance(old,list):
                value=[part.strip() for part in value.replace(';',',').split(',') if part.strip()]
                if key=='allowed_symbols':value=[part.upper() for part in value]
            elif key in ('max_positions','max_contracts','max_trades','consecutive_losses','cooldown_seconds','start_hour','end_hour','max_data_age_seconds','latency_bars'):value=int(value)
            elif key not in ('name','currency'):value=float(value.replace(',','.'))
            if key=='risk_fraction':value/=100
            data[section][key]=value
        data['strategy']['multi_timeframe']=self.multitimeframe.get()
        data['calendar']={'start':self.values[('calendar','start')].get(),'end':self.values[('calendar','end')].get(),
            'holidays':[day.strip() for day in self.values[('calendar','holidays')].get().split(',') if day.strip()],
            'verified':self.calendar_verified.get()} if self.calendar_enabled.get() else None
        symbol=self.instrument.get().strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{2,16}',symbol):raise ValueError('Código de ativo inválido')
        expiry=self.instrument_vars['expiry'].get().strip() or None
        if expiry:
            from datetime import date
            date.fromisoformat(expiry)
        spec=Instrument(symbol,float(self.instrument_vars['point_value'].get().replace(',','.')),
                        float(self.instrument_vars['tick'].get().replace(',','.')),int(self.instrument_vars['lot'].get()),
                        float(self.instrument_vars['margin'].get().replace(',','.')),expiry=expiry,
                        currency=self.instrument_vars['currency'].get().strip().upper(),allow_short=self.allow_short.get(),
                        volume_per_unit=float(self.instrument_vars['volume_per_unit'].get().replace(',','.')))
        data['instruments'][symbol]=asdict(spec)
        previous=self.dashboard.settings_text.get('1.0','end')
        self.dashboard.settings_text.delete('1.0','end');self.dashboard.settings_text.insert('1.0',json.dumps(data,indent=2))
        try:self.dashboard.apply_settings()
        except Exception:
            self.dashboard.settings_text.delete('1.0','end');self.dashboard.settings_text.insert('1.0',previous)
            raise
        self.window.destroy()
