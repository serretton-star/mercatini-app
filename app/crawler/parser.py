"""
app/crawler/parser.py
Parsing di date italiane e luoghi da testo libero (post IG, FB, web).
"""
import re
import logging
from datetime import date, datetime
from typing import Optional, Tuple

import dateparser

log = logging.getLogger(__name__)

# --- Mappa regioni italiane (anche abbreviazioni) ---
REGIONI = [
    "Abruzzo", "Basilicata", "Calabria", "Campania", "Emilia-Romagna",
    "Friuli-Venezia Giulia", "Friuli Venezia Giulia", "Lazio", "Liguria",
    "Lombardia", "Marche", "Molise", "Piemonte", "Puglia", "Sardegna",
    "Sicilia", "Toscana", "Trentino-Alto Adige", "Trentino Alto Adige",
    "Umbria", "Valle d'Aosta", "Valle d Aosta", "Veneto",
]
REGIONI_LOWER = {r.lower(): r for r in REGIONI}

# Province italiane (sigla -> nome regione)
PROVINCE_REGIONE = {
    "AG": "Sicilia", "AL": "Piemonte", "AN": "Marche", "AO": "Valle d'Aosta",
    "AR": "Toscana", "AP": "Marche", "AT": "Piemonte", "AV": "Campania",
    "BA": "Puglia", "BT": "Puglia", "BL": "Veneto", "BN": "Campania",
    "BG": "Lombardia", "BI": "Piemonte", "BO": "Emilia-Romagna", "BZ": "Trentino-Alto Adige",
    "BS": "Lombardia", "BR": "Puglia", "CA": "Sardegna", "CL": "Sicilia",
    "CB": "Molise", "CI": "Sardegna", "CE": "Campania", "CT": "Sicilia",
    "CZ": "Calabria", "CH": "Abruzzo", "CO": "Lombardia", "CS": "Calabria",
    "CR": "Lombardia", "KR": "Calabria", "CN": "Piemonte", "EN": "Sicilia",
    "FM": "Marche", "FE": "Emilia-Romagna", "FI": "Toscana", "FG": "Puglia",
    "FC": "Emilia-Romagna", "FR": "Lazio", "GE": "Liguria", "GO": "Friuli-Venezia Giulia",
    "GR": "Toscana", "IM": "Liguria", "IS": "Molise", "SP": "Liguria",
    "AQ": "Abruzzo", "LT": "Lazio", "LE": "Puglia", "LC": "Lombardia",
    "LI": "Toscana", "LO": "Lombardia", "LU": "Toscana", "MC": "Marche",
    "MN": "Lombardia", "MS": "Toscana", "MT": "Basilicata", "VS": "Sardegna",
    "ME": "Sicilia", "MI": "Lombardia", "MO": "Emilia-Romagna", "MB": "Lombardia",
    "NA": "Campania", "NO": "Piemonte", "NU": "Sardegna", "OG": "Sardegna",
    "OT": "Sardegna", "OR": "Sardegna", "PD": "Veneto", "PA": "Sicilia",
    "PR": "Emilia-Romagna", "PV": "Lombardia", "PG": "Umbria", "PU": "Marche",
    "PE": "Abruzzo", "PC": "Emilia-Romagna", "PI": "Toscana", "PT": "Toscana",
    "PN": "Friuli-Venezia Giulia", "PZ": "Basilicata", "PO": "Toscana",
    "RG": "Sicilia", "RA": "Emilia-Romagna", "RC": "Calabria", "RE": "Emilia-Romagna",
    "RI": "Lazio", "RN": "Emilia-Romagna", "RM": "Lazio", "RO": "Veneto",
    "SA": "Campania", "SS": "Sardegna", "SV": "Liguria", "SI": "Toscana",
    "SR": "Sicilia", "SO": "Lombardia", "TA": "Puglia", "TE": "Abruzzo",
    "TR": "Umbria", "TO": "Piemonte", "TP": "Sicilia", "TN": "Trentino-Alto Adige",
    "TV": "Veneto", "TS": "Friuli-Venezia Giulia", "UD": "Friuli-Venezia Giulia",
    "VA": "Lombardia", "VE": "Veneto", "VB": "Piemonte", "VC": "Piemonte",
    "VR": "Veneto", "VV": "Calabria", "VI": "Veneto", "VT": "Lazio",
}

DATEPARSER_SETTINGS = {
    'LOCALE_SPECIFIC_FORMATS': ['it'],
    'DATE_ORDER': 'DMY',
    'PREFER_DAY_OF_MONTH': 'first',
    'PREFER_DATES_FROM': 'future',
    'RETURN_AS_TIMEZONE_AWARE': False,
}

MESI_IT = {
    'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
    'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
    'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12,
    'gen': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'mag': 5, 'giu': 6,
    'lug': 7, 'ago': 8, 'set': 9, 'ott': 10, 'nov': 11, 'dic': 12,
}


def parse_date_it(text: str) -> Optional[date]:
    """Prova a estrarre una data da testo italiano."""
    if not text:
        return None
    try:
        dt = dateparser.parse(text, languages=['it'], settings=DATEPARSER_SETTINGS)
        if dt:
            return dt.date()
    except Exception:
        pass
    # Fallback regex: "12 ottobre 2025" / "12/10/2025" / "12-10-25"
    m = re.search(r'(\d{1,2})[/\-\s](\d{1,2})[/\-\s](\d{2,4})', text)
    if m:
        try:
            g, me, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if a < 100:
                a += 2000
            return date(a, me, g)
        except (ValueError, Exception):
            pass
    m = re.search(
        r'(\d{1,2})\s+(' + '|'.join(MESI_IT.keys()) + r')\s+(\d{4})',
        text.lower()
    )
    if m:
        try:
            g = int(m.group(1))
            me = MESI_IT[m.group(2)]
            a = int(m.group(3))
            return date(a, me, g)
        except (ValueError, KeyError):
            pass
    return None


def estrai_date(testo: str) -> Tuple[Optional[date], Optional[date]]:
    """
    Estrae (data_inizio, data_fine) da testo libero.
    Gestisce pattern come "12-13 ottobre", "dal 5 al 7 novembre 2025".
    """
    testo_lower = testo.lower()

    # Pattern "dal X al Y mese anno"
    m = re.search(
        r'dal[li]?\s+(\d{1,2})\s+al[li]?\s+(\d{1,2})\s+'
        r'(' + '|'.join(MESI_IT.keys()) + r')\s+(\d{4})',
        testo_lower
    )
    if m:
        try:
            g1, g2 = int(m.group(1)), int(m.group(2))
            me = MESI_IT[m.group(3)]
            a = int(m.group(4))
            return date(a, me, g1), date(a, me, g2)
        except (ValueError, KeyError):
            pass

    # Pattern "12-13 ottobre 2025" o "12 e 13 ottobre"
    m = re.search(
        r'(\d{1,2})[/\-e\s]+(\d{1,2})\s+'
        r'(' + '|'.join(MESI_IT.keys()) + r')[\s,]+(\d{4})',
        testo_lower
    )
    if m:
        try:
            g1, g2 = int(m.group(1)), int(m.group(2))
            me = MESI_IT[m.group(3)]
            a = int(m.group(4))
            return date(a, me, g1), date(a, me, g2)
        except (ValueError, KeyError):
            pass

    # Data singola
    d = parse_date_it(testo)
    return d, d


def estrai_luogo(testo: str) -> Tuple[str, str, str]:
    """
    Estrae (città, provincia, regione) da testo.
    Ritorna stringhe vuote se non trovato.
    """
    citta, provincia, regione = '', '', ''

    # Cerca regione
    for r_lower, r_nome in REGIONI_LOWER.items():
        if r_lower in testo.lower():
            regione = r_nome
            break

    # Cerca "(XX)" come provincia
    m = re.search(r'\(([A-Z]{2})\)', testo)
    if m:
        prov = m.group(1).upper()
        if prov in PROVINCE_REGIONE:
            provincia = prov
            if not regione:
                regione = PROVINCE_REGIONE[prov]

    # Cerca "a Città" / "in Città" / "presso Città"
    m = re.search(
        r'(?:a|in|presso|nel comune di|a\s+)\s+([A-ZÀÈÌÒÙ][a-zàèìòùA-Z\s]{2,25})'
        r'(?:\s*\([A-Z]{2}\))?',
        testo
    )
    if m:
        citta = m.group(1).strip()

    return citta, provincia, regione


def testo_e_mercatino(testo: str) -> bool:
    """Ritorna True se il testo sembra descrivere un mercatino/fiera."""
    keywords = [
        'mercatin', 'fiera', 'espositor', 'artigian', 'hobbist',
        'antiquari', 'vintage', 'collezion', 'handmade', 'fatto a mano',
        'bancarell', 'mostra mercato',
    ]
    testo_lower = testo.lower()
    return any(k in testo_lower for k in keywords)
