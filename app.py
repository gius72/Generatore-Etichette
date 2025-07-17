import streamlit as st
import pandas as pd
import os
from openpyxl import load_workbook
from openpyxl.styles import Alignment, PatternFill, Font
import re
import tempfile
import io
import base64

# Importa il template da Dropbox
from s3_template import get_template_from_url

def filtra_sap(df, area, rimorchio):
    """
    Filtra i dati SAP basandosi su area e rimorchio.
    Versione migliorata con logica identica al Generatore Etichette.py
    """
    df = df.copy()
    
    # Rimuovi duplicati basati su Viaggio
    df.drop_duplicates(subset="Viaggio", inplace=True)
    
    # Escludi NUMBER 1 LOGISTICS GROUP S.P.A. se presente
    if "DescrSpedizioniere" in df.columns:
        df = df[df["DescrSpedizioniere"] != "NUMBER 1 LOGISTICS GROUP S.P.A."]
    
    # Gestione valori nulli e vuoti per Rimorchio
    if "Rimorchio" in df.columns:
        df["Rimorchio"] = df["Rimorchio"].fillna("Orario Fisso")
        df.loc[df["Rimorchio"].astype(str).str.strip() == "", "Rimorchio"] = "Orario Fisso"
    
    # Filtro per area
    if area != "Tutti":
        if area == "Italia":
            df = df[df["Nazione Dest"] == "IT"]
        elif area == "Estero":
            df = df[df["Nazione Dest"] != "IT"]
    
    # Filtro per rimorchio - LOGICA MIGLIORATA
    if rimorchio != "Tutti":
        if rimorchio == "A Piazzale":
            df = df[df["Rimorchio"].astype(str).str.contains("A Piazzale", na=False)]
        elif rimorchio == "Orario Fisso":
            df = df[df["Rimorchio"].astype(str).str.contains("Orario Fisso", na=False)]
    
    return df.reset_index(drop=True)

def filtra_dpe(df, tipo_ingaggio, tipo_gestione):
    """
    Filtra i dati DPE basandosi su tipo ingaggio e tipo gestione.
    Versione migliorata con logica identica al Generatore Etichette.py
    """
    df = df.copy()
    
    # Trova le colonne dinamicamente (case-insensitive)
    veicolo_col = next((col for col in df.columns if col.strip().lower() == "veicolo"), None)
    trasportatore_col = next((col for col in df.columns if "trasportatore" in col.strip().lower()), None)
    tipo_ingaggio_col = next((col for col in df.columns if "tipo" in col.strip().lower() and "ingaggio" in col.strip().lower()), None)
    tipo_gestione_col = next((col for col in df.columns if "tipo" in col.strip().lower() and "gestione" in col.strip().lower()), None)
    dt_ingresso_prev_col = next((col for col in df.columns if "dt" in col.strip().lower() and "ingresso" in col.strip().lower() and "prev" in col.strip().lower()), None)
    targa_col = next((col for col in df.columns if "targa" in col.strip().lower() and "rimorchio" in col.strip().lower()), None)
    viaggio_col = next((col for col in df.columns if "viaggio" in col.strip().lower()), None)
    sequenza_col = next((col for col in df.columns if "sequenza" in col.strip().lower()), None)

    # Verifica presenza colonne obbligatorie
    if not tipo_ingaggio_col or not tipo_gestione_col or not dt_ingresso_prev_col:
        st.error("Colonne richieste non trovate nel file DPE.")
        return pd.DataFrame()
    
    # Filtro per tipo ingaggio
    if tipo_ingaggio != "Tutti":
        if tipo_ingaggio == "Viaggi":
            df = df[df[tipo_ingaggio_col].astype(str).str.contains("TRATTA", na=False, case=False)]
        elif tipo_ingaggio == "Spole":
            df = df[df[tipo_ingaggio_col].astype(str).str.contains("SPOLE", na=False, case=False)]
        elif tipo_ingaggio == "Rifugio":
            df = df[df[tipo_ingaggio_col].astype(str).str.contains("RIFUGIO", na=False, case=False)]

    # Filtro per tipo gestione
    if tipo_gestione != "Tutti":
        if tipo_gestione == "A Piazzale":
            df = df[df[tipo_gestione_col].astype(str).str.strip().str.upper() == "1 - A PIAZZALE"]
        elif tipo_gestione == "Orario Fisso":
            df = df[df[tipo_gestione_col].astype(str).str.strip().str.upper() == "2 - ORARIO FISSO"]

    # Rinomina le colonne per uniformità
    rename_map = {}
    if trasportatore_col:
        rename_map[trasportatore_col] = "Trasportatore"
    if veicolo_col:
        rename_map[veicolo_col] = "Veicolo"
    if targa_col:
        rename_map[targa_col] = "Targa Rimorchio Eff."
    if viaggio_col:
        rename_map[viaggio_col] = "Viaggio"
    if sequenza_col:
        rename_map[sequenza_col] = "Sequenza"
    if tipo_gestione_col:
        rename_map[tipo_gestione_col] = "Tipo Gestione"
    if tipo_ingaggio_col:
        rename_map[tipo_ingaggio_col] = "Tipo Ingaggio"
    if dt_ingresso_prev_col:
        rename_map[dt_ingresso_prev_col] = "Dt. Ingresso Prev."
    
    df = df.rename(columns=rename_map)

    # Ordina per data/ora se disponibile
    df = df.sort_values(by="Dt. Ingresso Prev.") if "Dt. Ingresso Prev." in df.columns else df
    return df.reset_index(drop=True)

def elabora_numerazione(df):
    """
    Applica la numerazione pari/dispari per ottimizzare la stampa delle etichette.
    """
    n = len(df)
    metà = n // 2
    dispari = list(range(1, metà * 2, 2))
    pari = list(range(2, n * 2 + 1, 2))
    numerazione = dispari[:metà] + pari[:n - metà]
    df["Ordine"] = numerazione
    df.sort_values(by="Ordine", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df

def clean_excel_text(value):
    """Pulisce il testo per Excel rimuovendo caratteri indesiderati."""
    if pd.isna(value):
        return ""
    value = str(value).replace('\r', '').replace('\n', '').strip()
    return value

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
    ws[cell].font = Font(color="FFFFFF", bold=True, size=28)
    ws[cell].fill = PatternFill("solid", fgColor="808080")
    ws[cell].alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)

def create_labels_from_template(df, template_path, output_path, filtro_dpe_tipo_ingaggio):
    """
    Crea le etichette Excel dal template utilizzando i dati filtrati.
    """
    wb = load_workbook(template_path)
    ws_template = wb.active
    total = len(df)
    
    for i in range(0, total, 2):
        ws_new = wb.copy_worksheet(ws_template)
        ws_new.title = f"Etichette_{(i // 2) + 1}"
        
        # --- ETICHETTA 1 ---
        if i < total:
            row1 = df.iloc[i]
            if "DescrSpedizioniere" in row1.index:  # SAP etichette
                ws_new["B6"].value = clean_excel_text(row1.get("DescrSpedizioniere", ""))
                ws_new["B14"].value = clean_excel_text(row1.get("Numero Targa", ""))
                ws_new["H14"].value = format_hhmm(row1.get("Ora Carico da", ""))
                ws_new["H14"].alignment = Alignment(wrap_text=False)
                ws_new["B22"].value = clean_excel_text(row1.get("Viaggio", ""))
                data_carico = row1.get("Data Carico", "")
                ws_new["H22"].value = format_ddmm(data_carico)
                ws_new["B29"].value = f"{clean_excel_text(row1.get('Sequenza fermate', ''))} [{clean_excel_text(row1.get('Nazione Dest', ''))}]"
                ws_new["H29"].value = clean_excel_text(row1.get("Rimorchio", ""))
            else:  # DPE etichette
                trasportatore = clean_excel_text(row1.get("Trasportatore", ""))
                veicolo = clean_excel_text(row1.get("Veicolo", ""))
                if veicolo and veicolo.lower() != "nan":
                    trasportatore = f"{trasportatore} ({veicolo})"
                ws_new["B6"].value = trasportatore
                
                targa = clean_excel_text(row1.get("Targa Rimorchio Eff.", ""))
                if targa.lower() == "nan":
                    targa = ""
                ws_new["B14"].value = targa
                
                dt = row1.get("Dt. Ingresso Prev.", "")
                tipo_ingaggio_val = str(row1.get("Tipo Ingaggio", "")).upper()
                if "SPOLE" in tipo_ingaggio_val:
                    set_spola_style(ws_new, "H14")
                else:
                    ws_new["H14"].value = format_hhmm(dt)
                    ws_new["H14"].alignment = Alignment(wrap_text=False)
                
                ws_new["B22"].value = clean_excel_text(row1.get("Viaggio", ""))
                ws_new["H22"].value = format_ddmm(dt)
                ws_new["B29"].value = f"{clean_excel_text(row1.get('Sequenza', ''))} [IT]"
                
                tipo_gestione = clean_excel_text(row1.get("Tipo Gestione", ""))
                tipo_gestione_out = "Orario Fisso" if tipo_gestione.strip().upper() == "2 - ORARIO FISSO" else "A Piazzale"
                ws_new["H29"].value = tipo_gestione_out
        
        # --- ETICHETTA 2 ---
        if i + 1 < total:
            row2 = df.iloc[i + 1]
            if "DescrSpedizioniere" in row2.index:  # SAP etichette
                ws_new["B38"].value = clean_excel_text(row2.get("DescrSpedizioniere", ""))
                ws_new["B46"].value = clean_excel_text(row2.get("Numero Targa", ""))
                ws_new["H46"].value = format_hhmm(row2.get("Ora Carico da", ""))
                ws_new["H46"].alignment = Alignment(wrap_text=False)
                ws_new["B54"].value = clean_excel_text(row2.get("Viaggio", ""))
                data_carico2 = row2.get("Data Carico", "")
                ws_new["H54"].value = format_ddmm(data_carico2)
                ws_new["H54"].alignment = Alignment(wrap_text=False)
                ws_new["B61"].value = f"{clean_excel_text(row2.get('Sequenza fermate', ''))} [{clean_excel_text(row2.get('Nazione Dest', ''))}]"
                ws_new["H61"].value = clean_excel_text(row2.get("Rimorchio", ""))
            else:  # DPE etichette
                trasportatore = clean_excel_text(row2.get("Trasportatore", ""))
                veicolo = clean_excel_text(row2.get("Veicolo", ""))
                if veicolo and veicolo.lower() != "nan":
                    trasportatore = f"{trasportatore} ({veicolo})"
                ws_new["B38"].value = trasportatore
                
                targa = clean_excel_text(row2.get("Targa Rimorchio Eff.", ""))
                if targa.lower() == "nan":
                    targa = ""
                ws_new["B46"].value = targa
                
                dt = row2.get("Dt. Ingresso Prev.", "")
                tipo_ingaggio_val2 = str(row2.get("Tipo Ingaggio", "")).upper()
                if "SPOLE" in tipo_ingaggio_val2:
                    set_spola_style(ws_new, "H46")
                else:
                    ws_new["H46"].value = format_hhmm(dt)
                    ws_new["H46"].alignment = Alignment(wrap_text=False)
                
                ws_new["B54"].value = clean_excel_text(row2.get("Viaggio", ""))
                ws_new["H54"].value = format_ddmm(dt)
                ws_new["H54"].alignment = Alignment(wrap_text=False)
                ws_new["B61"].value = f"{clean_excel_text(row2.get('Sequenza', ''))} [IT]"
                
                tipo_gestione = clean_excel_text(row2.get("Tipo Gestione", ""))
                tipo_gestione_out = "Orario Fisso" if tipo_gestione.strip().upper() == "2 - ORARIO FISSO" else "A Piazzale"
                ws_new["H61"].value = tipo_gestione_out
    
    try:
        wb.remove(ws_template)
        wb.save(output_path)
        return True, f"File etichette creato: {output_path}"
    except PermissionError:
        return False, f"Impossibile salvare il file '{output_path}'. Verifica che il file NON sia aperto in Excel e riprova."

def carica_file_csv_robusto(file):
    """
    Carica un file CSV provando diversi separatori e encoding.
    """
    separators = [";", ",", "\t", "|", " "]
    encodings = ["utf-8", "cp1252", "iso-8859-1", "latin1"]
    
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

def main():
    st.set_page_config(page_title="Generatore Etichette", layout="wide")
    
    st.title("Generatore Etichette")
    st.write("Carica i file SAP e DPE, scegli i filtri e genera le etichette in Excel.")

    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("File di input")
        sap_file = st.file_uploader("Carica file SAP (Excel)", type=["xlsx", "xls"])
        dpe_file = st.file_uploader("Carica file DPE (Excel o CSV)", type=["xlsx", "xls", "csv"])
        template_file = st.file_uploader("Carica template etichette (opzionale)", type=["xlsx"])
    
    with col2:
        st.subheader("Filtri")
        filtro_sap_area = st.selectbox("Area SAP", ["Tutti", "Italia", "Estero"])
        filtro_sap_rimorchio = st.selectbox("Rimorchio SAP", ["Tutti", "A Piazzale", "Orario Fisso"])
        filtro_dpe_tipo_ingaggio = st.selectbox("Tipo Ingaggio DPE", ["Tutti", "Viaggi", "Spole", "Rifugio"])
        filtro_dpe_tipo_gestione = st.selectbox("Tipo Gestione DPE", ["Tutti", "A Piazzale", "Orario Fisso"])
    
    col3, col4 = st.columns(2)
    
    with col3:
        stampa_sap = st.checkbox("Stampa SAP", value=True)
        stampa_dpe = st.checkbox("Stampa DPE", value=True)
    
    with col4:
        output_path = st.text_input("Nome file di output", "etichette_generate.xlsx")

    if st.button("Genera Etichette", type="primary"):
        # Caricamento template
        if template_file:
            # Usa il template caricato dall'utente
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                template_path = tmp.name
                tmp.write(template_file.read())
        else:
            try:
                # Prova a scaricare il template da GitHub
                template_path = get_template_from_url()
            except Exception as e:
                st.error(f"Non è stato possibile scaricare il template: {e}")
                st.info("Carica manualmente un template usando il campo 'Carica template etichette'.")
                return
        
        df_finale = pd.DataFrame()
        
        # Elaborazione file SAP
        if stampa_sap and sap_file is not None:
            try:
                df_sap = pd.read_excel(sap_file)
                df_sap_filtered = filtra_sap(df_sap, filtro_sap_area, filtro_sap_rimorchio)
                st.info(f"Righe SAP dopo filtro: {len(df_sap_filtered)}")
                df_finale = pd.concat([df_finale, df_sap_filtered], ignore_index=True)
            except Exception as e:
                st.error(f"Errore durante il caricamento del file SAP: {e}")
                return
        
        # Elaborazione file DPE
        if stampa_dpe and dpe_file is not None:
            try:
                if dpe_file.name.endswith(".csv"):
                    df_dpe = carica_file_csv_robusto(dpe_file)
                else:
                    df_dpe = pd.read_excel(dpe_file)
                
                df_dpe_filtered = filtra_dpe(df_dpe, filtro_dpe_tipo_ingaggio, filtro_dpe_tipo_gestione)
                st.info(f"Righe DPE dopo filtro: {len(df_dpe_filtered)}")
                df_finale = pd.concat([df_finale, df_dpe_filtered], ignore_index=True)
            except Exception as e:
                st.error(f"Errore durante il caricamento del file DPE: {e}")
                return
        
        if df_finale.empty:
            st.error("Nessun dato da elaborare dopo i filtri.")
            return
        
        st.info(f"Totale righe dopo concatenazione: {len(df_finale)}")
        
        # Ordinamento intelligente
        if stampa_sap and not stampa_dpe and "Ora Carico da" in df_finale.columns:
            st.info("Ordino SAP su 'Ora Carico da' crescente.")
            df_finale = df_finale.sort_values(by="Ora Carico da")
        elif stampa_dpe and not stampa_sap and "Dt. Ingresso Prev." in [c.strip() for c in df_finale.columns]:
            st.info("Ordino DPE su 'Dt. Ingresso Prev.' crescente.")
            df_finale = df_finale.sort_values(by="Dt. Ingresso Prev.")
        elif stampa_dpe and stampa_sap:
            st.info("Ordino SAP e DPE separatamente e li concateno.")
            if sap_file is not None:
                df_sap_orig = pd.read_excel(sap_file)
                sap_part = df_finale[df_finale.columns.intersection(df_sap_orig.columns)].copy()
                if "Ora Carico da" in sap_part.columns:
                    sap_part = sap_part.sort_values(by="Ora Carico da")
            else:
                sap_part = pd.DataFrame()
            
            if dpe_file is not None:
                if dpe_file.name.endswith(".csv"):
                    dpe_file.seek(0)
                    df_dpe_orig = carica_file_csv_robusto(dpe_file)
                else:
                    df_dpe_orig = pd.read_excel(dpe_file)
                
                dpe_part = df_finale[df_finale.columns.intersection(df_dpe_orig.columns)].copy()
                dpe_part.columns = [c.strip() for c in dpe_part.columns]
                if "Dt. Ingresso Prev." in dpe_part.columns:
                    dpe_part = dpe_part.sort_values(by="Dt. Ingresso Prev.")
            else:
                dpe_part = pd.DataFrame()
            
            df_finale = pd.concat([sap_part, dpe_part], ignore_index=True)
        
        # Applica numerazione pari/dispari
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