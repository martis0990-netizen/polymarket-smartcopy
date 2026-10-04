"""Keep the offline diagnostic's causal checks in existing CI, without new workflows."""
import pathlib
import subprocess
import sys


def test_market_regime_causal_contract():
    result = subprocess.run(
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'research',
         '-p', 'test_limitless_market_regime.py'],
        cwd=pathlib.Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
