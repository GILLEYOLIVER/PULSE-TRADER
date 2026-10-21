from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _write_crash_log(text: str) -> None:
    try:
        import os
        folder=Path(os.getenv('PULSE_DATA_DIR','.'));folder.mkdir(parents=True,exist_ok=True)
        (folder/'crash.log').write_text(text, encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    import argparse
    import os
    parser=argparse.ArgumentParser(description='PULSE-TRADER · somente PAPER')
    parser.add_argument('--data-dir')
    parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--output',default='pulse-smoke.json')
    args=parser.parse_args()
    if args.smoke_test:
        from trading_assistant.v2.selftest import run
        raise SystemExit(run(args.output))
    base=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    data_dir=Path(args.data_dir or os.getenv('PULSE_DATA_DIR') or base/'runtime').resolve()
    os.environ['PULSE_DATA_DIR']=str(data_dir)
    try:
        from trading_assistant.v2.dashboard import Dashboard
        Dashboard(data_dir).run()
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
#
