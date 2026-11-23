"""Golden list: vettori, container e localita' delle isole.

Le liste sono salvate in dati/golden_list.json nel repository: ogni ambiente
(main / test) legge il file del proprio branch, quindi restano separate.
Su Render il filesystem e' effimero: il salvataggio passa dalla GitHub Contents
API con un commit marcato [skip render] (nessun redeploy).
"""
import base64
import hashlib
import json
import os
import re
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

NOME_FILE = "dati/golden_list.json"
REPO_GITHUB = "gius72/Generatore-Etichette"
URL_API = f"https://api.github.com/repos/{REPO_GITHUB}/contents/{NOME_FILE}"
SOGLIA_VETTORI = 0.90
TTL_SECONDI = 60

VETTORI_PREDEFINITI = [
    "FUTURA CARGO SP.Z.O.O.",
    "COOP CO TRANS ARL",
    "FASULO CORPORATION SRL",
    "LOMBARDI SRL",
    "LKW  WALTER Internatioale",
    "AUTA MAROCCHI SPA",
    "NUMBER1 LOGISTICS GROUP",
]

LOCALITA_PREDEFINITE = {
    "SICILIA": ["PALERMO", "CATANIA", "MESSINA", "SIRACUSA", "RAGUSA", "TRAPANI",
                "AGRIGENTO", "CALTANISSETTA", "ENNA", "CARINI", "TERMINI IMERESE",
                "BAGHERIA", "PARTINICO", "MONREALE", "ACIREALE", "PATERNO", "ALCAMO",
                "MARSALA", "MAZARA DEL VALLO", "SCIACCA", "GELA", "VITTORIA", "LICATA",
                "AUGUSTA", "MELILLI", "PRIOLO GARGALLO", "AVOLA", "NOTO", "MODICA",
                "COMISO", "SCICLI", "ISPICA", "POZZALLO", "CALTAGIRONE", "MILAZZO",
                "PATTI", "CAPO D'ORLANDO", "CEFALU"],
    "SARDEGNA": ["CAGLIARI", "SASSARI", "OLBIA", "ORISTANO", "NUORO", "CARBONIA",
                 "IGLESIAS", "PORTO TORRES", "ALGHERO", "QUARTU SANT'ELENA",
                 "SELARGIUS", "ASSEMINI", "ELMAS", "CAPOTERRA", "SARROCH", "SESTU",
                 "SINNAI", "MONSERRATO", "PULA", "VILLACIDRO", "SANLURI", "MACOMER",
                 "OZIERI", "TEMPIO PAUSANIA", "ARZACHENA", "TORTOLI", "LANUSEI",
                 "MURAVERA", "PORTOSCUSO", "SANT'ANTIOCO"],
}

_CACHE = {"istante": 0.0, "dati": None}


def normalizza(testo):
    """Normalizza un nome per il confronto (maiuscole, accenti, punteggiatura)."""
    if testo is None:
        return ""
    testo = str(testo)
    testo = unicodedata.normalize("NFKD", testo)
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    testo = testo.upper()
    testo = re.sub(r"(?<=\d)(?=[A-Z])|(?<=[A-Z])(?=\d)", " ", testo)   # NUMBER1 -> NUMBER 1
    testo = re.sub(r"[^A-Z0-9]+", " ", testo)
    return re.sub(r"\s+", " ", testo).strip()


def similarita(primo, secondo):
    """Similarita' 0..1 fra due nomi, robusta a refusi e punteggiatura."""
    a, b = normalizza(primo), normalizza(secondo)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    token_a, token_b = set(a.split()), set(b.split())
    if token_a and token_b and (token_a <= token_b or token_b <= token_a) and min(len(token_a), len(token_b)) >= 2:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def vettore_in_golden_list(vettore, vettori):
    """Ritorna (trovato, voce_corrispondente, punteggio)."""
    if not normalizza(vettore):
        return False, "", 0.0
    migliore, punteggio = "", 0.0
    for voce in vettori or []:
        punto = similarita(vettore, voce)
        if punto > punteggio:
            migliore, punteggio = voce, punto
    return punteggio >= SOGLIA_VETTORI, migliore, punteggio


def isola_destinazione(regione, sequenza, localita):
    """SICILIA / SARDEGNA se la destinazione e' su un'isola, altrimenti stringa vuota."""
    regione_n = normalizza(regione)
    for isola in (localita or {}):
        nome_isola = normalizza(isola)
        if regione_n and nome_isola and nome_isola in regione_n:
            return isola
    segmenti = [normalizza(pezzo) for pezzo in re.split(r"[-\u2013\u2014+(),;:/]", str(sequenza or ""))]
    for isola, elenco in (localita or {}).items():
        nomi = {normalizza(nome) for nome in elenco if normalizza(nome)}
        for segmento in segmenti:
            if segmento and segmento in nomi:
                return isola
    return ""


def _struttura(dati):
    """Normalizza la struttura delle liste (chiavi mancanti, duplicati, ordinamento)."""
    dati = dati if isinstance(dati, dict) else {}
    vettori = [str(v).strip() for v in dati.get("vettori", []) if str(v).strip()]
    container = [str(v).strip() for v in dati.get("container", []) if str(v).strip()]
    localita = {}
    grezze = dati.get("localita", {})
    if isinstance(grezze, dict):
        for isola, elenco in grezze.items():
            nomi = [str(n).strip() for n in elenco if str(n).strip()] if isinstance(elenco, list) else []
            localita[str(isola).strip().upper()] = sorted(set(nomi), key=str.upper)
    if not localita:
        localita = {k: sorted(set(v), key=str.upper) for k, v in LOCALITA_PREDEFINITE.items()}
    return {
        "vettori": sorted(set(vettori), key=str.upper) or list(VETTORI_PREDEFINITI),
        "container": sorted(set(container), key=str.upper),
        "localita": localita,
    }


def percorso_locale():
    return Path(__file__).resolve().parent / NOME_FILE


def carica_liste(usa_cache=True):
    """Legge le liste dal file incluso nel deploy (fallback ai valori predefiniti)."""
    adesso = time.time()
    if usa_cache and _CACHE["dati"] is not None and adesso - _CACHE["istante"] < TTL_SECONDI:
        return _CACHE["dati"]

    dati = None
    percorso = percorso_locale()
    try:
        if percorso.is_file():
            dati = json.loads(percorso.read_text(encoding="utf-8"))
    except Exception:
        dati = None

    dati = _struttura(dati)
    _CACHE["dati"] = dati
    _CACHE["istante"] = adesso
    return dati


def branch_corrente():
    return os.environ.get("RENDER_GIT_BRANCH", "").strip()


def salva_liste(dati):
    """Salva le liste: file locale e, se c'e' il token, commit sul branch corrente.

    Ritorna (ok, messaggio).
    """
    dati = _struttura(dati)
    contenuto = json.dumps(dati, ensure_ascii=False, indent=2) + "\n"

    percorso = percorso_locale()
    try:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_text(contenuto, encoding="utf-8")
        ok_locale = True
    except Exception as errore:
        ok_locale = False
        messaggio_locale = f"file locale non scritto: {errore}"
    else:
        messaggio_locale = "file locale aggiornato"

    _CACHE["dati"] = dati
    _CACHE["istante"] = time.time()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    branch = branch_corrente()
    if not token or not branch:
        return ok_locale, (
            "Liste salvate sul server (" + messaggio_locale + "). "
            "Token GitHub o branch non disponibili: nessun commit sul repository."
        )

    try:
        import requests
    except Exception as errore:
        return ok_locale, f"Liste salvate sul server ({messaggio_locale}); requests non disponibile: {errore}"

    intestazioni = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        risposta = requests.get(URL_API, headers=intestazioni, params={"ref": branch}, timeout=15)
        sha = risposta.json().get("sha") if risposta.status_code == 200 else None

        corpo = {
            "message": "[skip render] golden list: aggiornamento liste",
            "content": base64.b64encode(contenuto.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            corpo["sha"] = sha
        risposta = requests.put(URL_API, headers=intestazioni, json=corpo, timeout=20)
        if risposta.status_code in (200, 201):
            return True, f"Liste salvate e commit su GitHub (branch {branch})."
        return ok_locale, f"Liste salvate sul server; commit GitHub non riuscito ({risposta.status_code})."
    except Exception as errore:
        return ok_locale, f"Liste salvate sul server; errore nel commit GitHub: {errore}"


def hash_password(password):
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


def password_valida(password):
    atteso = os.environ.get("ADMIN_PASSWORD_SHA256", "").strip().lower()
    if not atteso:
        return False
    return hash_password(password).lower() == atteso
