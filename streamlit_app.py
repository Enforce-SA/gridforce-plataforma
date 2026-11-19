"""Ponto de entrada por omissão do Streamlit Cloud: corre app.py."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")
