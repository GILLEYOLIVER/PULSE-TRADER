import sys
from pathlib import Path

# garante project root no sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_assistant.diagnostics import run_diagnostics, print_diagnostics

if __name__ == '__main__':
    raise SystemExit(print_diagnostics(run_diagnostics()))
