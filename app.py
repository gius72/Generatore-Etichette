import streamlit as st
import pandas as pd
import os
from openpyxl import load_workbook
from openpyxl.styles import Alignment, PatternFill, Font, Border, Side
import re
import tempfile
import io
import base64

# Importa il template da GitHub
from s3_template import get_template_from_url

# ---------------------------------------------------------------------------
# Costanti ATL
# ---------------------------------------------------------------------------
ATL_ROW_HEIGHT = 35      # altezza righe 2-3 e 34-35 in pt
ATL_FONT_SIZE  = 52      # dimensione font "ATL"
ATL_BORDER = Border(
    left=Side(style="medium"),
    right=Side(style="medium"),
    top=Side(style="medium"),
    bottom=Side(style="none"),
)
ATL_BORDER_BOTTOM = Border(
    left=Side(style="medium"),
    right=Side(style="medium"),
    top=Side(style="none"),
    bottom=Side(style="medium"),
)

# ---------------------------------------------------------------------------
# Costanti orario SAP (viaggi NUMBER 1)
# ---------------------------------------------------------------------------
NUMBER1_SPEDIZIONIERE = "NUMBER 1 LOGISTICS GROUP S.P.A."
ORA_SAP_BORDER = Border(
    left=Side(style="medium"),
    right=Side(style="medium"),
    top=Side(style="medium"),
    bottom=Side(style="medium"),
)

# Larghezza (unita' Excel) della fessura tra riquadro orario e riquadro ATL
ORA_SAP_LARGHEZZA_FESSURA = 4.0

# Larghezze delle colonne del template (fallback se la dimensione non e' definita)
LARGHEZZE_TEMPLATE = {
    "A": 5.42578125, "B": 11.42578125, "C": 11.42578125, "D": 11.42578125,
    "E": 11.42578125, "F": 64.42578125, "G": 1.5703125, "H": 22.85546875,
}

# ---------------------------------------------------------------------------
# Funzioni di filtro
# ---------------------------------------------------------------------------

def filtra_sap(df, area, rimorchio):
    """Filtra i dati SAP basandosi su area e rimorchio."""
    df = df.copy()
    df.drop_duplicates(subset="Viaggio", inplace=True)

    if "DescrSpedizioniere" in df.columns:
        df = df[df["DescrSpedizioniere"] != "NUMBER 1 LOGISTICS GROUP S.P.A."]

    if "Rimorchio" in df.columns:
        df["Rimorchio"] = df["Rimorchio"].fillna("Orario Fisso")
        df.loc[df["Rimorchio"].astype(str).str.strip() == "", "Rimorchio"] = "Orario Fisso"

    if area != "Tutti":
        if area == "Italia":
            df = df[df["Nazione Dest"] == "IT"]
        elif area == "Estero":
            df = df[df["Nazione Dest"] != "IT"]

    if rimorchio != "Tutti":
        if rimorchio == "A Piazzale":
            df = df[df["Rimorchio"].astype(str).str.contains("A Piazzale", na=False)]
        elif rimorchio == "Orario Fisso":
            df = df[df["Rimorchio"].astype(str).str.contains("Orario Fisso", na=False)]

    return df.reset_index(drop=True)


def estrai_orari_number1(df_sap):
    """
    Restituisce {viaggio: orario di carico SAP} per le righe con
    DescrSpedizioniere = NUMBER 1 LOGISTICS GROUP S.P.A.

    Queste righe non generano etichette SAP (l'orario utile viene preso dal DPE),
    ma l'orario SAP va comunque stampato in un riquadro sull'etichetta DPE.
    """
    colonne_necessarie = {"DescrSpedizioniere", "Viaggio", "Ora Carico da"}
    if not colonne_necessarie.issubset(set(df_sap.columns)):
        return {}

    mask  = df_sap["DescrSpedizioniere"].astype(str).str.strip() == NUMBER1_SPEDIZIONIERE
    orari = {}
    for _, riga in df_sap[mask].iterrows():
        viaggio = clean_excel_text(riga.get("Viaggio", ""))
        if not viaggio or viaggio in orari:
            continue
        orari[viaggio] = riga.get("Ora Carico da", "")
    return orari


def filtra_dpe(df, tipo_ingaggio, tipo_gestione):
    """Filtra i dati DPE basandosi su tipo ingaggio e tipo gestione."""
    df = df.copy()

    veicolo_col        = next((c for c in df.columns if c.strip().lower() == "veicolo"), None)
    trasportatore_col  = next((c for c in df.columns if "trasportatore" in c.strip().lower()), None)
    tipo_ingaggio_col  = next((c for c in df.columns if "tipo" in c.strip().lower() and "ingaggio" in c.strip().lower()), None)
    tipo_gestione_col  = next((c for c in df.columns if "tipo" in c.strip().lower() and "gestione" in c.strip().lower()), None)
    dt_ingresso_prev_col = next((c for c in df.columns if "dt" in c.strip().lower() and "ingresso" in c.strip().lower() and "prev" in c.strip().lower()), None)
    targa_col          = next((c for c in df.columns if "targa" in c.strip().lower() and "rimorchio" in c.strip().lower()), None)
    viaggio_col        = next((c for c in df.columns if "viaggio" in c.strip().lower()), None)
    sequenza_col       = next((c for c in df.columns if "sequenza" in c.strip().lower()), None)
    note_ing_col       = next((c for c in df.columns if "note" in c.strip().lower() and "ing" in c.strip().lower()), None)
    # Fallback: colonna che contiene solo "note" se quella con "ing" non esiste
    if note_ing_col is None:
        note_ing_col = next((c for c in df.columns if c.strip().lower() == "note"), None)

    if not tipo_ingaggio_col or not tipo_gestione_col or not dt_ingresso_prev_col:
        st.error("Colonne richieste non trovate nel file DPE.")
        return pd.DataFrame()

    if tipo_ingaggio != "Tutti":
        if tipo_ingaggio == "Viaggi":
            df = df[df[tipo_ingaggio_col].astype(str).str.contains("TRATTA", na=False, case=False)]
        elif tipo_ingaggio == "Spole":
            df = df[df[tipo_ingaggio_col].astype(str).str.contains("SPOLE", na=False, case=False)]
        elif tipo_ingaggio == "Rifugio":
            df = df[df[tipo_ingaggio_col].astype(str).str.contains("RIFUGIO", na=False, case=False)]

    if tipo_gestione != "Tutti":
        if tipo_gestione == "A Piazzale":
            df = df[df[tipo_gestione_col].astype(str).str.strip().str.upper() == "1 - A PIAZZALE"]
        elif tipo_gestione == "Orario Fisso":
            df = df[df[tipo_gestione_col].astype(str).str.strip().str.upper() == "2 - ORARIO FISSO"]

    rename_map = {}
    if trasportatore_col:  rename_map[trasportatore_col]      = "Trasportatore"
    if veicolo_col:        rename_map[veicolo_col]             = "Veicolo"
    if targa_col:          rename_map[targa_col]               = "Targa Rimorchio Eff."
    if viaggio_col:        rename_map[viaggio_col]             = "Viaggio"
    if sequenza_col:       rename_map[sequenza_col]            = "Sequenza"
    if tipo_gestione_col:  rename_map[tipo_gestione_col]       = "Tipo Gestione"
    if tipo_ingaggio_col:  rename_map[tipo_ingaggio_col]       = "Tipo Ingaggio"
    if dt_ingresso_prev_col: rename_map[dt_ingresso_prev_col]  = "Dt. Ingresso Prev."
    if note_ing_col:       rename_map[note_ing_col]            = "Note Ing."

    df = df.rename(columns=rename_map)
    # Sort nel main con na_position="last" — qui non serve
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Funzione ATL
# ---------------------------------------------------------------------------

# Quante righe iniziali scansionare per trovare l'intestazione del file ATL
ATL_MAX_RIGHE_INTESTAZIONE = 10


def _intestazione_viaggio(valore):
    """True se il valore sembra l'intestazione della colonna viaggio."""
    testo = str(valore).strip().lower()
    return "viaggio" in testo and ("nr" in testo or "numero" in testo)


def _intestazione_flag(valore):
    """True se il valore sembra l'intestazione della colonna flag ATL."""
    testo = str(valore).strip().lower()
    return ("carico" in testo and "automatico" in testo) or ("eligible" in testo)


def _leggi_atl_grezzo(atl_file):
    """
    Legge il file ATL senza assumere che l'intestazione sia la prima riga
    (header=None). Prova prima Excel, poi CSV con diversi separatori ed encoding.
    Restituisce un DataFrame grezzo oppure None.
    """
    nome_file = str(getattr(atl_file, "name", "")).lower()

    if nome_file.endswith(".csv"):
        for sep in [";", ",", "\t", "|"]:
            for enc in ["utf-8", "cp1252", "iso-8859-1", "latin1"]:
                try:
                    atl_file.seek(0)
                    df_grezzo = pd.read_csv(atl_file, sep=sep, encoding=enc, header=None)
                    if len(df_grezzo.columns) > 1:
                        return df_grezzo
                except Exception:
                    continue
        return None

    try:
        atl_file.seek(0)
        return pd.read_excel(atl_file, header=None)
    except Exception:
        return None


def _rileva_riga_intestazione(df_grezzo, max_righe=ATL_MAX_RIGHE_INTESTAZIONE):
    """
    Cerca nelle prime righe del file quella che contiene le intestazioni ATL.
    Restituisce l'indice (0-based) della riga di intestazione, oppure None.
    Preferisce la riga che contiene sia la colonna viaggio sia quella flag.
    """
    candidati = []
    for idx in range(min(len(df_grezzo), max_righe)):
        valori = df_grezzo.iloc[idx].tolist()
        if any(_intestazione_viaggio(v) for v in valori):
            ha_flag = any(_intestazione_flag(v) for v in valori)
            candidati.append((idx, ha_flag))

    for idx, ha_flag in candidati:
        if ha_flag:
            return idx
    if candidati:
        return candidati[0][0]
    return None


def _intestazioni_univoche(valori):
    """Converte una riga di intestazione in un elenco di nomi colonna univoci."""
    intestazioni = []
    for i, v in enumerate(valori):
        nome = "" if pd.isna(v) else str(v).strip()
        if not nome:
            nome = f"Col_{i + 1}"
        base, suffisso = nome, 2
        while nome in intestazioni:
            nome = f"{base}_{suffisso}"
            suffisso += 1
        intestazioni.append(nome)
    return intestazioni


def leggi_tabella_atl(atl_file):
    """
    Legge il file ATL (Excel o CSV) rilevando automaticamente la riga di
    intestazione: può essere la prima riga oppure una riga successiva
    (es. la quarta, dopo alcune righe di preambolo).

    Restituisce la tupla (df, numero_riga_intestazione 1-based) oppure (None, None).
    """
    df_grezzo = _leggi_atl_grezzo(atl_file)
    if df_grezzo is None or df_grezzo.empty:
        st.error("File ATL: impossibile leggere il file o file vuoto.")
        return None, None

    idx_intestazione = _rileva_riga_intestazione(df_grezzo)
    if idx_intestazione is None:
        st.error(
            "File ATL: intestazione non trovata nelle prime "
            f"{ATL_MAX_RIGHE_INTESTAZIONE} righe. Prime righe lette:\n"
            f"{df_grezzo.head(5).to_string(index=False, header=False)}"
        )
        return None, None

    df_atl = df_grezzo.iloc[idx_intestazione + 1:].copy()
    df_atl.columns = _intestazioni_univoche(df_grezzo.iloc[idx_intestazione].tolist())
    df_atl = df_atl.reset_index(drop=True)

    return df_atl, idx_intestazione + 1


def carica_atl(atl_file):
    """
    Legge il file ATL (Excel o CSV) e restituisce un set di valori
    della colonna 'Nr. Viaggio' dove 'Carico Automatico' == 1.
    La riga di intestazione viene rilevata automaticamente (prima riga o successive).
    """
    try:
        df_atl, riga_intestazione = leggi_tabella_atl(atl_file)
        if df_atl is None:
            return set()

        if riga_intestazione > 1:
            st.info(f"File ATL: intestazione rilevata alla riga {riga_intestazione}.")

        # Trova colonna numero viaggio: "Nr. Viaggio" o "Numero Viaggio" (case-insensitive)
        nr_viaggio_col = next((
            c for c in df_atl.columns
            if ("nr" in c.strip().lower() and "viaggio" in c.strip().lower())
            or ("numero" in c.strip().lower() and "viaggio" in c.strip().lower())
        ), None)

        # Trova colonna flag: "Carico Automatico" o "Eligible" (case-insensitive)
        carico_auto_col = next((
            c for c in df_atl.columns
            if ("carico" in c.strip().lower() and "automatico" in c.strip().lower())
            or ("eligible" in c.strip().lower())
        ), None)

        if nr_viaggio_col is None or carico_auto_col is None:
            st.error(
                f"File ATL: colonne non trovate (intestazione letta alla riga {riga_intestazione}). "
                f"Colonne presenti: {list(df_atl.columns)}"
            )
            return set()

        # Valori considerati "attivo" per Carico Automatico o Eligible
        valori_attivi = {"1", "y", "yes", "true", "si", "sì"}
        df_atl_filtrato = df_atl[
            df_atl[carico_auto_col].astype(str).str.strip().str.lower().isin(valori_attivi)
        ]

        # Restituisce un set di Nr. Viaggio (come stringhe normalizzate),
        # scartando le righe vuote in coda al file
        viaggi_atl = set(df_atl_filtrato[nr_viaggio_col].astype(str).str.strip())
        viaggi_atl -= {"", "nan", "none"}
        return viaggi_atl

    except Exception as e:
        st.error(f"Errore nel caricamento del file ATL: {e}")
        return set()


def applica_flag_atl(df, viaggi_atl):
    """
    Aggiunge la colonna 'is_atl' al dataframe confrontando
    la colonna 'Viaggio' con il set di viaggi ATL.
    """
    if "Viaggio" in df.columns and viaggi_atl:
        df["is_atl"] = df["Viaggio"].astype(str).str.strip().isin(viaggi_atl)
    else:
        df["is_atl"] = False
    return df


# ---------------------------------------------------------------------------
# Funzioni di supporto Excel
# ---------------------------------------------------------------------------

def elabora_numerazione(df):
    """Applica la numerazione pari/dispari per ottimizzare la stampa."""
    n = len(df)
    metà = n // 2
    dispari = list(range(1, metà * 2, 2))
    pari    = list(range(2, n * 2 + 1, 2))
    numerazione = dispari[:metà] + pari[:n - metà]
    df["Ordine"] = numerazione
    df.sort_values(by="Ordine", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def clean_excel_text(value):
    """Pulisce il testo per Excel rimuovendo caratteri indesiderati.
    Converte float interi (es. 5205.0) in interi (5205)."""
    if pd.isna(value):
        return ""
    # Se è un float con parte decimale zero, converti in int prima di stringare
    if isinstance(value, float) and value == int(value):
        value = int(value)
    return str(value).replace('\r', '').replace('\n', '').strip()


def formato_viaggio_dpe(row):
    """
    Restituisce il valore da scrivere nella cella VIAGGIO per le etichette DPE.
    Se 'Note Ing.' è presente e non vuota: 'NOTE (VIAGGIO)'
    Altrimenti: 'VIAGGIO'
    """
    viaggio = clean_excel_text(row.get("Viaggio", ""))
    nota    = clean_excel_text(row.get("Note Ing.", ""))
    if nota:
        return f"{nota} ({viaggio})"
    return viaggio


def calcola_font_viaggio(testo, font_base=88):
    """
    Restituisce 57pt se il testo contiene una nota concatenata (parentesi),
    altrimenti il font base 88pt.
    """
    if "(" in testo:
        return 57
    return font_base


def format_hhmm(value):
    """Formatta i valori di tempo in formato HH:MM."""
    if pd.isna(value) or value == "":
        return ""
    try:
        dt = pd.to_datetime(value, errors="coerce")
        if not pd.isna(dt):
            return dt.strftime("%H:%M")
        val = str(value).strip()
        if re.match(r"^\d{1,2}\.\d{2}(:\d{2})?$", val):
            val = val.replace(".", ":")
        if re.match(r"^\d{1,2}:\d{2}:\d{2}$", val):
            hh, mm, _ = val.split(":")
            return f"{hh.zfill(2)}:{mm}"
        if re.match(r"^\d{1,2}:\d{2}$", val):
            hh, mm = val.split(":")
            return f"{hh.zfill(2)}:{mm}"
        return val
    except Exception:
        return str(value).strip()


def format_ddmm(value):
    """Formatta le date in formato DD/MM."""
    if pd.isna(value) or value == "":
        return ""
    try:
        return pd.to_datetime(value, errors="coerce").strftime("%d/%m")
    except Exception:
        return str(value)


def set_spola_style(ws, cell):
    """Formatta la cella con lo stile SPOLA (grigio con testo bianco)."""
    ws[cell].value = "SPOLA"
    ws[cell].font      = Font(color="FFFFFF", bold=True, size=28)
    ws[cell].fill      = PatternFill("solid", fgColor="808080")
    ws[cell].alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)


def scrivi_atl_cell(ws, cella_top, cella_bottom, merge_range):
    """
    Scrive la cella ATL in F2:F3 (etichetta 1) o F34:F35 (etichetta 2).
    - Imposta altezza righe, unisce celle, scrive testo con font/bordi.
    """
    # Altezza righe
    top_row    = int(cella_top[1:])
    bottom_row = int(cella_bottom[1:])
    ws.row_dimensions[top_row].height    = ATL_ROW_HEIGHT
    ws.row_dimensions[bottom_row].height = ATL_ROW_HEIGHT

    # Merge e contenuto
    ws.merge_cells(merge_range)
    ws[cella_top].value     = "ATL"
    ws[cella_top].font      = Font(name="Arial", size=ATL_FONT_SIZE, bold=True)
    ws[cella_top].alignment = Alignment(horizontal="center", vertical="center")
    ws[cella_top].border    = ATL_BORDER
    ws[cella_bottom].border = ATL_BORDER_BOTTOM


def _larghezza_effettiva(ws, lettera):
    """
    Larghezza effettiva di una colonna, tenendo conto che il template definisce
    le larghezze come range (es. <col min="2" max="5"/> copre B..E).
    """
    indice = "ABCDEFGH".index(lettera) + 1
    for dim in ws.column_dimensions.values():
        if (dim.width is not None and dim.min is not None and dim.max is not None
                and dim.min <= indice <= dim.max):
            return dim.width
    return LARGHEZZE_TEMPLATE[lettera]


def crea_fessura_orario(ws):
    """
    Crea una piccola fessura tra il riquadro orario e il riquadro ATL:
    restringe la colonna E e sposta la larghezza tolta sulla colonna A
    (fuori dall'area di stampa B1:H63), cosi' l'etichetta da B a H resta identica.
    Idempotente e sicura sui range di colonne: riscrive le larghezze per singola
    colonna (evita <col> sovrapposti che Excel interpreta in modo ambiguo).
    """
    if getattr(ws, "_fessura_orario", False):
        return

    larghezze = {lettera: _larghezza_effettiva(ws, lettera) for lettera in "ABCDEFGH"}
    if larghezze["E"] <= ORA_SAP_LARGHEZZA_FESSURA:
        return

    delta = larghezze["E"] - ORA_SAP_LARGHEZZA_FESSURA
    larghezze["E"] = ORA_SAP_LARGHEZZA_FESSURA
    larghezze["A"] += delta

    for chiave in list(ws.column_dimensions):
        del ws.column_dimensions[chiave]
    for posizione, lettera in enumerate("ABCDEFGH", start=1):
        dim = ws.column_dimensions[lettera]
        dim.min = dim.max = posizione
        dim.width = larghezze[lettera]   # customWidth e' derivato dalla width

    ws._fessura_orario = True


def scrivi_orario_sap_cell(ws, cella_top, cella_bottom, merge_range, orario, font_orario):
    """
    Scrive il riquadro con l'orario SAP in C2:D3 (etichetta 1) o C34:D35
    (etichetta 2), cioe' in alto a sinistra del riquadro ATL, con la colonna E
    che fa da fessura di separazione.
    - Stessa altezza righe del riquadro ATL, merge, font dell'orario SAP (H14)
      e bordo su tutto il perimetro.
    """
    # Fessura tra riquadro orario e riquadro ATL
    crea_fessura_orario(ws)

    top_row    = int(re.sub(r"[A-Z]", "", cella_top))
    bottom_row = int(re.sub(r"[A-Z]", "", cella_bottom))
    ws.row_dimensions[top_row].height    = ATL_ROW_HEIGHT
    ws.row_dimensions[bottom_row].height = ATL_ROW_HEIGHT

    ws.merge_cells(merge_range)

    # Bordo su tutte le celle del riquadro, altrimenti il perimetro resta incompleto
    for riga in ws[merge_range]:
        for cella in riga:
            cella.border = ORA_SAP_BORDER

    cella = ws[cella_top]
    cella.value     = orario
    cella.font      = Font(name=font_orario.name, size=font_orario.size,
                           bold=font_orario.bold)
    cella.alignment = Alignment(horizontal="center", vertical="center")
    cella.border    = ORA_SAP_BORDER


# ---------------------------------------------------------------------------
# Generazione etichette
# ---------------------------------------------------------------------------

def create_labels_from_template(df, template_path, output_path, filtro_dpe_tipo_ingaggio):
    """Crea le etichette Excel dal template."""
    wb = load_workbook(template_path)
    ws_template = wb.active
    total = len(df)

    # Font dell'orario SAP nel template (H14): stesso tipo/dimensione nel riquadro
    font_orario = ws_template["H14"].font

    for i in range(0, total, 2):
        ws_new = wb.copy_worksheet(ws_template)
        ws_new.title = f"Etichette_{(i // 2) + 1}"

        # Flag ATL per le due etichette del foglio
        is_atl_1 = bool(df.iloc[i].get("is_atl", False))       if i     < total else False
        is_atl_2 = bool(df.iloc[i + 1].get("is_atl", False))   if i + 1 < total else False

        # Stampa cella ATL se necessario
        if is_atl_1:
            scrivi_atl_cell(ws_new, "F2",  "F3",  "F2:F3")
        if is_atl_2:
            scrivi_atl_cell(ws_new, "F34", "F35", "F34:F35")

        # Riquadro orario SAP (viaggi NUMBER 1), a sinistra del riquadro ATL
        ora_sap_1 = format_hhmm(df.iloc[i].get("Ora SAP", ""))     if i     < total else ""
        ora_sap_2 = format_hhmm(df.iloc[i + 1].get("Ora SAP", "")) if i + 1 < total else ""

        # Altezze uniformi delle fasce superiori: se una delle due etichette ha un
        # riquadro (ATL o orario), entrambe devono avere la stessa altezza, altrimenti
        # le due etichette non sono piu' a meta' foglio e il taglio taglia il contenuto.
        if is_atl_1 or is_atl_2 or ora_sap_1 or ora_sap_2:
            for riga in (2, 3, 34, 35):
                ws_new.row_dimensions[riga].height = ATL_ROW_HEIGHT

        if ora_sap_1:
            scrivi_orario_sap_cell(ws_new, "C2",  "D3",  "C2:D3",   ora_sap_1, font_orario)
        if ora_sap_2:
            scrivi_orario_sap_cell(ws_new, "C34", "D35", "C34:D35", ora_sap_2, font_orario)

        # --- ETICHETTA 1 ---
        if i < total:
            row1 = df.iloc[i]
            if str(row1.get("_source", "")).upper() == "SAP":  # SAP
                ws_new["B6"].value  = clean_excel_text(row1.get("DescrSpedizioniere", ""))
                ws_new["B14"].value = clean_excel_text(row1.get("Numero Targa", ""))
                ws_new["H14"].value = format_hhmm(row1.get("Ora Carico da", ""))
                ws_new["H14"].alignment = Alignment(wrap_text=False)
                ws_new["B22"].value = clean_excel_text(row1.get("Viaggio", ""))
                ws_new["H22"].value = format_ddmm(row1.get("Data Carico", ""))
                ws_new["B29"].value = f"{clean_excel_text(row1.get('Sequenza fermate', ''))} [{clean_excel_text(row1.get('Nazione Dest', ''))}]"
                ws_new["H29"].value = clean_excel_text(row1.get("Rimorchio", ""))
            else:  # DPE
                trasportatore = clean_excel_text(row1.get("Trasportatore", ""))
                veicolo       = clean_excel_text(row1.get("Veicolo", ""))
                if veicolo and veicolo.lower() != "nan":
                    trasportatore = f"{trasportatore} ({veicolo})"
                ws_new["B6"].value = trasportatore

                targa = clean_excel_text(row1.get("Targa Rimorchio Eff.", ""))
                if targa.lower() == "nan":
                    targa = ""
                ws_new["B14"].value = targa

                dt = row1.get("Dt. Ingresso Prev.", "")
                if "SPOLE" in str(row1.get("Tipo Ingaggio", "")).upper():
                    set_spola_style(ws_new, "H14")
                else:
                    ws_new["H14"].value = format_hhmm(dt)
                    ws_new["H14"].alignment = Alignment(wrap_text=False)

                viaggio_text = formato_viaggio_dpe(row1)
                ws_new["B22"].value = viaggio_text
                ws_new["B22"].font  = Font(name="Lato Black", size=calcola_font_viaggio(viaggio_text), bold=True)
                ws_new["B22"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
                ws_new["H22"].value = format_ddmm(dt)
                ws_new["B29"].value = f"{clean_excel_text(row1.get('Sequenza', ''))} [IT]"

                tipo_gestione = clean_excel_text(row1.get("Tipo Gestione", ""))
                ws_new["H29"].value = "Orario Fisso" if tipo_gestione.strip().upper() == "2 - ORARIO FISSO" else "A Piazzale"

        # --- ETICHETTA 2 ---
        if i + 1 < total:
            row2 = df.iloc[i + 1]
            if str(row2.get("_source", "")).upper() == "SAP":  # SAP
                ws_new["B38"].value = clean_excel_text(row2.get("DescrSpedizioniere", ""))
                ws_new["B46"].value = clean_excel_text(row2.get("Numero Targa", ""))
                ws_new["H46"].value = format_hhmm(row2.get("Ora Carico da", ""))
                ws_new["H46"].alignment = Alignment(wrap_text=False)
                ws_new["B54"].value = clean_excel_text(row2.get("Viaggio", ""))
                ws_new["H54"].value = format_ddmm(row2.get("Data Carico", ""))
                ws_new["H54"].alignment = Alignment(wrap_text=False)
                ws_new["B61"].value = f"{clean_excel_text(row2.get('Sequenza fermate', ''))} [{clean_excel_text(row2.get('Nazione Dest', ''))}]"
                ws_new["H61"].value = clean_excel_text(row2.get("Rimorchio", ""))
            else:  # DPE
                trasportatore = clean_excel_text(row2.get("Trasportatore", ""))
                veicolo       = clean_excel_text(row2.get("Veicolo", ""))
                if veicolo and veicolo.lower() != "nan":
                    trasportatore = f"{trasportatore} ({veicolo})"
                ws_new["B38"].value = trasportatore

                targa = clean_excel_text(row2.get("Targa Rimorchio Eff.", ""))
                if targa.lower() == "nan":
                    targa = ""
                ws_new["B46"].value = targa

                dt = row2.get("Dt. Ingresso Prev.", "")
                if "SPOLE" in str(row2.get("Tipo Ingaggio", "")).upper():
                    set_spola_style(ws_new, "H46")
                else:
                    ws_new["H46"].value = format_hhmm(dt)
                    ws_new["H46"].alignment = Alignment(wrap_text=False)

                viaggio_text = formato_viaggio_dpe(row2)
                ws_new["B54"].value = viaggio_text
                ws_new["B54"].font  = Font(name="Lato Black", size=calcola_font_viaggio(viaggio_text), bold=True)
                ws_new["B54"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
                ws_new["H54"].value = format_ddmm(dt)
                ws_new["H54"].alignment = Alignment(wrap_text=False)
                ws_new["B61"].value = f"{clean_excel_text(row2.get('Sequenza', ''))} [IT]"

                tipo_gestione = clean_excel_text(row2.get("Tipo Gestione", ""))
                ws_new["H61"].value = "Orario Fisso" if tipo_gestione.strip().upper() == "2 - ORARIO FISSO" else "A Piazzale"

    try:
        wb.remove(ws_template)
        wb.save(output_path)
        return True, f"File etichette creato: {output_path}"
    except PermissionError:
        return False, f"Impossibile salvare '{output_path}'. Verifica che il file NON sia aperto e riprova."


def carica_file_csv_robusto(file):
    """Carica un file CSV provando diversi separatori e encoding."""
    separators = [";", ",", "\t", "|", " "]
    encodings  = ["utf-8", "cp1252", "iso-8859-1", "latin1"]

    for sep in separators:
        for enc in encodings:
            try:
                file.seek(0)
                df = pd.read_csv(file, encoding=enc, sep=sep)
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue

    raise ValueError("Impossibile caricare il file CSV con i separatori e encoding disponibili")


# ---------------------------------------------------------------------------
# UI principale
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Generatore Etichette", layout="wide")
    st.title("Generatore Etichette")
    st.write("Carica i file SAP e DPE, scegli i filtri e genera le etichette in Excel.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("File di input")
        sap_file      = st.file_uploader("Carica file SAP (Excel)",            type=["xlsx", "xls"])
        dpe_file      = st.file_uploader("Carica file DPE (Excel o CSV)",       type=["xlsx", "xls", "csv"])
        atl_file      = st.file_uploader("Carica file ATL (Excel o CSV) — opzionale", type=["xlsx", "xls", "csv"])
        template_file = st.file_uploader("Carica template etichette (opzionale)", type=["xlsx"])

    with col2:
        st.subheader("Filtri SAP")
        filtro_sap_area      = st.selectbox("Area SAP",       ["Tutti", "Italia", "Estero"])
        filtro_sap_rimorchio = st.selectbox("Rimorchio SAP",  ["Tutti", "A Piazzale", "Orario Fisso"])
        filtro_sap_atl       = st.selectbox("ATL SAP",        ["Tutti", "Solo ATL", "No ATL"],
                                             help="Filtra le etichette SAP in base alla presenza nel file ATL")

        st.subheader("Filtri DPE")
        filtro_dpe_tipo_ingaggio = st.selectbox("Tipo Ingaggio DPE", ["Tutti", "Viaggi", "Spole", "Rifugio"])
        filtro_dpe_tipo_gestione = st.selectbox("Tipo Gestione DPE", ["Tutti", "A Piazzale", "Orario Fisso"])
        filtro_dpe_atl           = st.selectbox("ATL DPE",           ["Tutti", "Solo ATL", "No ATL"],
                                                 help="Filtra le etichette DPE in base alla presenza nel file ATL")

    col3, col4 = st.columns(2)

    with col3:
        stampa_sap = st.checkbox("Stampa SAP", value=True)
        stampa_dpe = st.checkbox("Stampa DPE", value=True)

    with col4:
        output_path = st.text_input("Nome file di output", "etichette_generate.xlsx")

    if st.button("Genera Etichette", type="primary"):

        # Avviso se si usano filtri ATL senza file ATL
        usa_filtro_atl = (filtro_sap_atl != "Tutti" or filtro_dpe_atl != "Tutti")
        if usa_filtro_atl and atl_file is None:
            st.warning("Hai selezionato un filtro ATL ma non hai caricato il file ATL. I filtri ATL verranno ignorati.")
            # Resetta i filtri ATL a "Tutti" per evitare comportamenti inattesi
            filtro_sap_atl = "Tutti"
            filtro_dpe_atl = "Tutti"

        # Caricamento template
        if template_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                template_path = tmp.name
                tmp.write(template_file.read())
        else:
            try:
                template_path = get_template_from_url()
            except Exception as e:
                st.error(f"Non è stato possibile scaricare il template: {e}")
                st.info("Carica manualmente un template usando il campo apposito.")
                return

        # Caricamento file ATL
        viaggi_atl = set()
        if atl_file is not None:
            viaggi_atl = carica_atl(atl_file)
            if viaggi_atl:
                st.info(f"File ATL caricato: {len(viaggi_atl)} viaggi con Carico Automatico = 1")
            else:
                st.warning("File ATL caricato ma nessun viaggio trovato con Carico Automatico = 1.")

        df_sap_filtered = pd.DataFrame()
        df_dpe_filtered = pd.DataFrame()
        orari_number1   = {}

        # ----------------------------------------------------------------
        # Elaborazione SAP
        # ----------------------------------------------------------------
        # Orari SAP dei viaggi NUMBER 1: servono anche con "Stampa SAP" disattivato
        df_sap_grezzo = None
        if sap_file is not None:
            try:
                sap_file.seek(0)
                df_sap_grezzo = pd.read_excel(sap_file)
                orari_number1 = estrai_orari_number1(df_sap_grezzo)
                if orari_number1:
                    st.info(f"Orari SAP per viaggi NUMBER 1: {len(orari_number1)}")
            except Exception as e:
                st.error(f"Errore durante il caricamento del file SAP: {e}")
                return

        if stampa_sap and df_sap_grezzo is not None:
            try:
                df_sap = df_sap_grezzo

                df_sap_filtered = filtra_sap(df_sap, filtro_sap_area, filtro_sap_rimorchio)

                # Flag ATL
                df_sap_filtered = applica_flag_atl(df_sap_filtered, viaggi_atl)

                # Filtro ATL — applicato sempre se l'utente ha scelto un filtro,
                # anche se viaggi_atl è vuoto (in quel caso "Solo ATL" → 0 righe)
                if filtro_sap_atl == "Solo ATL" and atl_file is not None:
                    df_sap_filtered = df_sap_filtered[df_sap_filtered["is_atl"]]
                elif filtro_sap_atl == "No ATL" and atl_file is not None:
                    df_sap_filtered = df_sap_filtered[~df_sap_filtered["is_atl"]]

                # Ordina per ora di carico
                if "Ora Carico da" in df_sap_filtered.columns:
                    df_sap_filtered = df_sap_filtered.sort_values(by="Ora Carico da", na_position="last")

                # Marca l'origine
                df_sap_filtered["_source"] = "SAP"

                st.info(f"Righe SAP dopo filtro: {len(df_sap_filtered)}")
            except Exception as e:
                st.error(f"Errore durante il caricamento del file SAP: {e}")
                return

        # ----------------------------------------------------------------
        # Elaborazione DPE
        # ----------------------------------------------------------------
        if stampa_dpe and dpe_file is not None:
            try:
                if dpe_file.name.endswith(".csv"):
                    df_dpe = carica_file_csv_robusto(dpe_file)
                else:
                    df_dpe = pd.read_excel(dpe_file)

                df_dpe_filtered = filtra_dpe(df_dpe, filtro_dpe_tipo_ingaggio, filtro_dpe_tipo_gestione)

                # Flag ATL
                df_dpe_filtered = applica_flag_atl(df_dpe_filtered, viaggi_atl)

                # Filtro ATL — applicato sempre se l'utente ha scelto un filtro,
                # anche se viaggi_atl è vuoto (in quel caso "Solo ATL" → 0 righe)
                if filtro_dpe_atl == "Solo ATL" and atl_file is not None:
                    df_dpe_filtered = df_dpe_filtered[df_dpe_filtered["is_atl"]]
                elif filtro_dpe_atl == "No ATL" and atl_file is not None:
                    df_dpe_filtered = df_dpe_filtered[~df_dpe_filtered["is_atl"]]

                # Il sort avviene già in filtra_dpe dopo il rename delle colonne.
                # Qui riapplichiamo con na_position esplicito per robustezza.
                if "Dt. Ingresso Prev." in df_dpe_filtered.columns:
                    df_dpe_filtered = df_dpe_filtered.sort_values(by="Dt. Ingresso Prev.", na_position="last")

                # Marca l'origine
                df_dpe_filtered["_source"] = "DPE"

                st.info(f"Righe DPE dopo filtro: {len(df_dpe_filtered)}")
            except Exception as e:
                st.error(f"Errore durante il caricamento del file DPE: {e}")
                return

        # ----------------------------------------------------------------
        # Concatenazione — ogni df è già ordinato, _source traccia l'origine
        # ----------------------------------------------------------------
        df_finale = pd.concat([df_sap_filtered, df_dpe_filtered], ignore_index=True)

        if df_finale.empty:
            st.error("Nessun dato da elaborare dopo i filtri.")
            return

        st.info(f"Totale righe dopo concatenazione: {len(df_finale)}")

        # Assicura che is_atl esista sempre
        if "is_atl" not in df_finale.columns:
            df_finale["is_atl"] = False

        # Orario SAP (viaggi NUMBER 1) da stampare sulle etichette DPE
        if orari_number1 and "Viaggio" in df_finale.columns:
            df_finale["Ora SAP"] = (
                df_finale["Viaggio"].astype(str).str.strip().map(orari_number1)
            )
        else:
            df_finale["Ora SAP"] = ""

        # Numerazione pari/dispari
        st.info("Applico numerazione pari/dispari...")
        df_finale = elabora_numerazione(df_finale)

        # Genera etichette
        with st.spinner("Generazione etichette in corso..."):
            success, msg = create_labels_from_template(df_finale, template_path, output_path, filtro_dpe_tipo_ingaggio)

        if success:
            st.success(msg)
            with open(output_path, "rb") as file:
                st.download_button(
                    label="Scarica file etichette",
                    data=file,
                    file_name=output_path,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.error(msg)


if __name__ == "__main__":
    main()
