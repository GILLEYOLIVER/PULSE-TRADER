from __future__ import annotations
"""Adapter (interface) para ProfitDLL.

IMPORTANTE:
- Este arquivo é intencionalmente um *stub* (sem chamadas reais), para você plugar a DLL no seu ambiente.
- O padrão recomendado é: callback => colocar Tick/Book em fila => engine processa fora do callback.

Você vai implementar:
- connect()
- subscribe(symbol)
- start_event_loop() (para manter callbacks vivos)
"""
from dataclasses import dataclass
from typing import Callable, Optional
from datetime import datetime, timezone
from trader_tool.domain.models import Tick

@dataclass
class ProfitCallbacks:
    on_tick: Callable[[Tick], None]
    # você pode adicionar book/tinybook aqui futuramente

class ProfitDLLConnector:
    def __init__(self, callbacks: ProfitCallbacks):
        self.callbacks = callbacks
        self.connected = False

    def connect_market(self, user: str, password: str, key: str):
        # TODO: carregar DLL via ctypes, chamar init/login, setar callbacks.
        self.connected = True

    def subscribe(self, symbol: str):
        # TODO: DLLSubscribeTicker / SubscribeOfferBook etc.
        pass

    def start_event_loop(self):
        # TODO: manter o loop da DLL rodando, se necessário.
        pass

    # Exemplo de como você chamaria seu callback internamente:
    def _emit_fake_tick(self, symbol: str, price: float):
        t = Tick(ts=datetime.now(timezone.utc), symbol=symbol, price=price)
        self.callbacks.on_tick(t)
