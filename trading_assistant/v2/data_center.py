"""Desktop controls for public data, explicit Profit CSV conversion and read-only refresh."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, filedialog

from .company_context import fetch_company_context
from .market_data import fetch_market, read_profit_csv


PERIODS={'1 s':1,'5 s':5,'10 s':10,'15 s':15,'30 s':30,'1 min':60,'5 min':300,'15 min':900,'60 min':3600,'Diário':86400}

def provider_periods(provider):
    supported={60,900,3600,86400} if provider=='mercado_bitcoin' else set(PERIODS.values()) if provider=='binance' else {60,300,900,3600,86400}
    return tuple(label for label,seconds in PERIODS.items() if seconds in supported)


class DataCenter:
    def __init__(self,panel):
        self.panel=panel
        self.dashboard=panel.dashboard
        self.timer=None
        self.closed=False
        self.settings_path=self.dashboard.data_dir/'feed-settings.json'
        self.settings={'provider':'brapi','symbol':'PETR4','period':'Diário','auto':False,'context':True}
        if self.settings_path.exists():
            try:
                saved=json.loads(self.settings_path.read_text(encoding='utf-8'))
                if not isinstance(saved,dict) or saved.get('provider') not in ('brapi','mercado_bitcoin','binance') or saved.get('period') not in PERIODS:
                    raise ValueError('Configuração da fonte inválida')
                self.settings.update(saved)
            except (ValueError,OSError):
                self.settings['auto']=False
        if self.settings.get('auto'):
            self.timer=self.dashboard.root.after(1000,self._tick)

    def open(self):
        window=tk.Toplevel(self.dashboard.root)
        window.title('Fontes de dados · somente leitura')
        window.geometry('730x520')
        provider=tk.StringVar(value=self.settings['provider'])
        symbol=tk.StringVar(value=self.settings['symbol'])
        period=tk.StringVar(value=self.settings['period'])
        auto=tk.BooleanVar(value=self.settings['auto'])
        context=tk.BooleanVar(value=self.settings['context'])
        ttk.Label(window,padding=16,wraplength=680,text=(
            'Dados públicos de ações: PETR4, VALE3, ITUB4 e MGLU3 na brapi. Outros ativos dependem do plano e da variável BRAPI_TOKEN. '
            'Cripto: BTC/ETH em BRL no Mercado Bitcoin; BTCUSDT/ETHUSDT em USDT na Binance, com atividade do candle. Cotações podem ter atraso. '
            'Segundos na Binance: última hora, formada a partir de candles de 1 s. '
            'WIN/WDO: use um histórico autorizado do Profit. Nenhum acesso a conta ou envio de ordens.')).pack(fill='x')
        form=ttk.Frame(window,padding=16);form.pack(fill='x')
        for row,(label,var,choices) in enumerate((('Provedor',provider,('brapi','mercado_bitcoin','binance')),
                    ('Ativo',symbol,None),('Período',period,tuple(PERIODS)))):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=6)
            widget=ttk.Combobox(form,textvariable=var,values=choices,state='readonly') if choices else ttk.Entry(form,textvariable=var)
            widget.grid(row=row,column=1,sticky='ew',padx=12,pady=6)
            if var is provider:provider_widget=widget
            if var is period:period_widget=widget
        def update_periods(_=None):
            values=provider_periods(provider.get());period_widget.configure(values=values)
            if period.get() not in values:period.set('1 min')
        provider_widget.bind('<<ComboboxSelected>>',update_periods);update_periods()
        form.columnconfigure(1,weight=1)
        ttk.Checkbutton(window,text='Consultar fundamentos, proventos e comunicados CVM para ações',variable=context).pack(anchor='w',padx=16)
        ttk.Checkbutton(window,text='Atualizar automaticamente a cada 60 segundos (somente leitura)',variable=auto).pack(anchor='w',padx=16,pady=8)
        def apply():
            self.settings={'provider':provider.get(),'symbol':symbol.get().strip().upper(),'period':period.get(),'auto':auto.get(),'context':context.get()}
            if self.settings['period'] not in PERIODS:raise ValueError('Período inválido')
            temporary=self.settings_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.settings,indent=2),encoding='utf-8');temporary.replace(self.settings_path)
            self.refresh()
        ttk.Button(window,text='Salvar e consultar',command=lambda:self.dashboard.guard(apply)).pack(anchor='w',padx=16,pady=6)
        ttk.Button(window,text='Converter CSV exportado do Profit',command=lambda:self.dashboard.guard(self.import_profit)).pack(anchor='w',padx=16,pady=6)
        ttk.Label(window,padding=16,wraplength=680,text='A atualização mantém o catálogo de análise. Ela não avança o replay nem envia ordens. O contexto de empresas é renovado no máximo uma vez por dia. Credenciais não são gravadas pelo aplicativo.').pack(fill='x')

    def refresh(self):
        if self.closed:return
        if self.timer is not None:
            self.dashboard.root.after_cancel(self.timer);self.timer=None
        if self.dashboard.jobs.busy:
            if self.settings.get('auto'):
                self.timer=self.dashboard.root.after(1000,self._tick);return
            raise ValueError('Aguarde a tarefa atual antes de consultar a fonte')
        settings=dict(self.settings)
        self.dashboard.status.set('Consultando dados públicos em segundo plano…')
        def work():
            market=fetch_market(settings['symbol'],PERIODS[settings['period']],provider=settings['provider'],
                                window='1h' if PERIODS[settings['period']]<60 else '2y' if settings['period']=='Diário' else '5d')
            market.save(self.dashboard.data_dir/'downloads')
            context=None
            path=self.dashboard.data_dir/'company-context'/(settings['symbol']+'.json')
            if settings['context'] and settings['provider']=='brapi':
                from datetime import datetime,timezone
                if not path.exists() or datetime.now(timezone.utc).timestamp()-path.stat().st_mtime>86400:
                    try:context=fetch_company_context(settings['symbol'],path.parent)
                    except ValueError as error:context={'error':str(error)}
            return market,context
        def done(result):
            market,context=result
            self.panel.add_bars(market.bars)
            self.panel.profile.set('Dias e semanas · diário' if market.bars[0].seconds==86400 else 'No dia · minutos e horas')
            self.panel.analyze()
            self.dashboard.status.set(f"Dados {market.bars[0].source}: {len(market.bars)} candles encerrados · {market.provenance['last_closed_at']}")
            if context and context.get('error'):self.panel.notice.set('Histórico atualizado. Contexto parcial: '+context['error'])
            if self.settings.get('auto') and not self.closed:
                self.timer=self.dashboard.root.after(60000,self._tick)
        def failed(error):
            self.dashboard.status.set('Dados preservados; consulta falhou: '+str(error))
            if self.settings.get('auto') and not self.closed:
                self.timer=self.dashboard.root.after(60000,self._tick)
            else:self.dashboard.background_error(error)
        self.dashboard.jobs.start(work,done,failed)

    def _tick(self):
        self.timer=None
        if not self.closed and self.settings.get('auto'):
            try:self.refresh()
            except Exception as error:
                self.dashboard.status.set('Atualização de dados interrompida: '+str(error))
                self.timer=self.dashboard.root.after(60000,self._tick)

    def import_profit(self):
        path=filedialog.askopenfilename(parent=self.dashboard.root,title='CSV exportado do Profit',filetypes=[('CSV','*.csv'),('Texto','*.txt')])
        if not path:return
        window=tk.Toplevel(self.dashboard.root);window.title('Converter histórico do Profit');window.geometry('640x330')
        period=tk.StringVar(value='1 min');symbol=tk.StringVar();clock=tk.StringVar(value='Abertura')
        ttk.Label(window,padding=12,wraplength=600,text='Selecione o período real do arquivo e a convenção do horário. Volume Quantidade é obrigatório; Volume Financeiro não será usado como liquidez. Se não existir coluna Ativo, informe o código.').pack(fill='x')
        form=ttk.Frame(window,padding=12);form.pack(fill='x')
        for row,(label,var,choices) in enumerate((('Período',period,tuple(PERIODS)),('Horário do candle',clock,('Abertura','Encerramento')),('Ativo se ausente no CSV',symbol,None))):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=5)
            widget=ttk.Combobox(form,textvariable=var,values=choices,state='readonly') if choices else ttk.Entry(form,textvariable=var)
            widget.grid(row=row,column=1,padx=8,pady=5)
        def convert():
            seconds=PERIODS[period.get()];ticker=symbol.get().strip() or None;kind='open' if clock.get()=='Abertura' else 'close'
            self.dashboard.jobs.start(lambda:read_profit_csv(path,seconds=seconds,symbol=ticker,timestamp_kind=kind),lambda bars:self.panel.add_bars(bars))
            window.destroy();self.dashboard.status.set('Convertendo histórico do Profit em segundo plano…')
        ttk.Button(window,text='Converter e importar',command=lambda:self.dashboard.guard(convert)).pack(anchor='w',padx=12,pady=12)

    def close(self):
        self.closed=True
        if self.timer is not None:
            self.dashboard.root.after_cancel(self.timer);self.timer=None
