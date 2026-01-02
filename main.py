from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _write_crash_log(text: str) -> None:
    try:
        Path("crash.log").write_text(text, encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    try:
        from trading_assistant.ui.dashboard import launch_dashboard
        launch_dashboard()
    except Exception as e:
        tb = traceback.format_exc()
        msg = f"Erro ao iniciar o app: {type(e).__name__}: {e}\n\n{tb}"
        _write_crash_log(msg)
        print(msg)

        # tenta mostrar uma mensagem visual (se tkinter estiver disponível)
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "PULSE-TRADER - Erro ao iniciar",
                "O app falhou ao iniciar.\n\n"
                "• Veja o arquivo 'crash.log' na pasta do projeto\n"
                "• Ou rode 'python run_diagnostico.py' para checar dependências\n\n"
                f"Erro: {type(e).__name__}: {e}",
            )
            root.destroy()
        except Exception:
            pass

        # se você abriu clicando duas vezes, isso ajuda a não fechar instantaneamente
        if sys.stdout is None or not sys.stdout.isatty():
            return
        try:
            input("\nPressione ENTER para fechar... ")
        except Exception:
            pass


if __name__ == "__main__":
    main()
