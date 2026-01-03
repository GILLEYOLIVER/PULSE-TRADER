from __future__ import annotations

import importlib
import platform
import sys
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _try_import(mod: str) -> Tuple[bool, str]:
    try:
        importlib.import_module(mod)
        return True, "import OK"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def run_diagnostics() -> List[CheckResult]:
    results: List[CheckResult] = []

    # Python / plataforma
    results.append(
        CheckResult(
            name="python",
            ok=True,
            detail=f"{sys.version.split()[0]} | exec={sys.executable}",
        )
    )
    results.append(CheckResult(name="platform", ok=True, detail=platform.platform()))

    # Dependências que mais causam 'abre e fecha'
    for mod in [
        "tkinter",
        "customtkinter",
        "matplotlib",
        "matplotlib.backends.backend_tkagg",
        "requests",
        "dateutil",
        "gdeltdoc",
    ]:
        ok, detail = _try_import(mod)
        results.append(CheckResult(name=f"import:{mod}", ok=ok, detail=detail))

    # Imports do próprio app
    for mod in [
        "trading_assistant.config",
        "trading_assistant.core.models",
        "trading_assistant.ui.dashboard",
        "trading_assistant.app",
    ]:
        ok, detail = _try_import(mod)
        results.append(CheckResult(name=f"import:{mod}", ok=ok, detail=detail))

    # Smoke test do pipeline (sem GUI) — não usa internet se mock_mode=True
    try:
        import asyncio
        from trading_assistant.config import TradingAssistantConfig
        from trading_assistant.app import run_market_pipeline

        async def _smoke() -> None:
            cfg = TradingAssistantConfig()
            cfg.market_feed.mock_mode = True
            cfg.news_feed.mock_mode = True
            await run_market_pipeline(cfg, runtime_seconds=2)

        asyncio.run(_smoke())
        results.append(CheckResult(name="pipeline_smoke", ok=True, detail="OK (2s)"))
    except Exception as e:
        results.append(CheckResult(name="pipeline_smoke", ok=False, detail=f"{type(e).__name__}: {e}"))

    return results


def print_diagnostics(results: List[CheckResult]) -> int:
    ok_all = True
    print("\n=== PULSE-TRADER | Diagnóstico ===\n")
    for r in results:
        status = "OK" if r.ok else "FALHOU"
        print(f"[{status}] {r.name}: {r.detail}")
        ok_all = ok_all and r.ok

    if ok_all:
        print("\n✅ Tudo certo. Se o app ainda fecha sozinho, rode pelo terminal/PyCharm para ver o traceback.")
        return 0

    print("\n❌ Tem dependência/import falhando. Corrija os itens marcados como FALHOU.")
    return 1


if __name__ == "__main__":
    raise SystemExit(print_diagnostics(run_diagnostics()))
