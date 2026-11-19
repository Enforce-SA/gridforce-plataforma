"""Biblioteca de projetos partilhada (ficheiros .json).

Os projetos ficam num repositório GitHub PRIVADO, separado do código (que é público), para
não se perderem quando a página é atualizada ou o Streamlit Cloud reinicia. Configuração nos
segredos do Streamlit (ou variáveis de ambiente):

    GRIDFORCE_LIB_TOKEN = "github_pat_..."     # token com acesso de leitura e escrita a "Contents"
    GRIDFORCE_LIB_REPO  = "Enforce-SA/gridforce-projetos"   # opcional
    GRIDFORCE_LIB_FOLDER = "projetos_qualidade"              # opcional (ambiente de Qualidade)

Sem token, a biblioteca usa uma pasta local (só dura até a aplicação reiniciar).
"""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

import requests

DEFAULT_REPO = "Enforce-SA/gridforce-projetos"
FOLDER = "projetos"  # o ambiente de Qualidade usa outra pasta (GRIDFORCE_LIB_FOLDER)
LOCAL = Path(__file__).resolve().parent.parent / "biblioteca"
API = "https://api.github.com"


def _secret(name: str) -> str | None:
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(name)
    except Exception:  # noqa: BLE001
        return None


def _cfg():
    global FOLDER
    FOLDER = _secret("GRIDFORCE_LIB_FOLDER") or "projetos"
    return _secret("GRIDFORCE_LIB_TOKEN"), _secret("GRIDFORCE_LIB_REPO") or DEFAULT_REPO


def is_shared() -> bool:
    return bool(_cfg()[0])


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def safe_name(name: str) -> str:
    s = re.sub(r"[^\w\-. ]", "", name, flags=re.UNICODE).strip().replace(" ", "_")
    return (s or "projeto")[:80] + ".json"


TOKEN_EXPIRY: str | None = None   # data de expiração da chave, lida das respostas do GitHub


def days_to_expiry() -> int | None:
    """Dias até a chave da biblioteca expirar (None se não se souber)."""
    if not TOKEN_EXPIRY:
        return None
    import datetime as dt
    try:
        d = dt.datetime.strptime(TOKEN_EXPIRY[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d - dt.date.today()).days


def list_projects() -> list[str]:
    """Nomes dos ficheiros na biblioteca, ordenados."""
    token, repo = _cfg()
    if not token:
        return sorted(p.name for p in LOCAL.glob("*.json")) if LOCAL.exists() else []
    r = requests.get(f"{API}/repos/{repo}/contents/{FOLDER}", headers=_headers(token), timeout=30)
    global TOKEN_EXPIRY
    TOKEN_EXPIRY = r.headers.get("github-authentication-token-expiration") or TOKEN_EXPIRY
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return sorted(x["name"] for x in r.json() if x["name"].endswith(".json"))


def load_project(fname: str) -> dict:
    token, repo = _cfg()
    if not token:
        return json.loads((LOCAL / fname).read_text(encoding="utf-8"))
    r = requests.get(f"{API}/repos/{repo}/contents/{FOLDER}/{fname}", headers=_headers(token), timeout=30)
    r.raise_for_status()
    return json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))


def save_project(d: dict, fname: str | None = None, author: str = "GridForce") -> str:
    """Grava (cria ou substitui) um projeto. Devolve o nome do ficheiro."""
    fname = fname or safe_name(d.get("Nome do projeto", "projeto"))
    body = json.dumps(d, ensure_ascii=False, indent=2)
    token, repo = _cfg()
    if not token:
        LOCAL.mkdir(exist_ok=True)
        (LOCAL / fname).write_text(body, encoding="utf-8")
        return fname
    url = f"{API}/repos/{repo}/contents/{FOLDER}/{fname}"
    h = _headers(token)
    cur = requests.get(url, headers=h, timeout=30)
    payload = {"message": f"{author}: guardar {fname}", "content": base64.b64encode(body.encode("utf-8")).decode()}
    if cur.status_code == 200:
        payload["sha"] = cur.json()["sha"]
    r = requests.put(url, headers=h, json=payload, timeout=30)
    r.raise_for_status()
    return fname


def delete_project(fname: str, author: str = "GridForce") -> None:
    token, repo = _cfg()
    if not token:
        (LOCAL / fname).unlink(missing_ok=True)
        return
    url = f"{API}/repos/{repo}/contents/{FOLDER}/{fname}"
    h = _headers(token)
    cur = requests.get(url, headers=h, timeout=30)
    if cur.status_code != 200:
        return
    r = requests.delete(url, headers=h, json={"message": f"{author}: apagar {fname}", "sha": cur.json()["sha"]},
                        timeout=30)
    r.raise_for_status()
