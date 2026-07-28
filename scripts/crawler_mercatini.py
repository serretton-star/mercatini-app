#!/usr/bin/env python3
"""
crawler_mercatini.py
Crawler settimanale per nuovi mercatini artigianali italiani.
Cerca sulle sorgenti configurate, usa Claude AI per estrarre dati strutturati,
inserisce le bozze nel DB (pubblicato=False) per l'approvazione admin.
"""
import os, sys, json, logging
from datetime import date, datetime, timezone

sys.path.insert(0, '/var/www/mercatini')
os.environ.setdefault('FLASK_ENV', 'production')

import requests
from bs4 import BeautifulSoup
import anthropic

from app import create_app, db
from app.models import Mercatino, Categoria

# ─── Costanti ──────────────────────────────────────────────────────────────
LOG_PATH       = '/var/www/mercatini/logs/crawler.log'
ADMIN_USER_ID  = 2        # serretto.n@gmail.com
CAT_ARTIGIANATO_ID = 1   # Artigianato

OGGI       = date.today()
MAX_GIORNI = 90
DATA_FINE_RICERCA = OGGI + __import__('datetime').timedelta(days=MAX_GIORNI)

# ─── Logging ───────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('crawler')

# ─── Mappa provincia → regione ─────────────────────────────────────────────
PROV_REGIONE = {
    'AG':'Sicilia','AL':'Piemonte','AN':'Marche','AO':'Valle d\'Aosta',
    'AP':'Marche','AQ':'Abruzzo','AR':'Toscana','AT':'Piemonte',
    'AV':'Campania','BA':'Puglia','BG':'Lombardia','BI':'Piemonte',
    'BL':'Veneto','BN':'Campania','BO':'Emilia-Romagna','BR':'Puglia',
    'BS':'Lombardia','BT':'Puglia','BZ':'Trentino-Alto Adige',
    'CA':'Sardegna','CB':'Molise','CE':'Campania','CH':'Abruzzo',
    'CL':'Sicilia','CN':'Piemonte','CO':'Lombardia','CR':'Lombardia',
    'CS':'Calabria','CT':'Sicilia','CZ':'Calabria','EN':'Sicilia',
    'FC':'Emilia-Romagna','FE':'Emilia-Romagna','FG':'Puglia',
    'FI':'Toscana','FM':'Marche','FR':'Lazio','GE':'Liguria',
    'GO':'Friuli-Venezia Giulia','GR':'Toscana','IM':'Liguria',
    'IS':'Molise','KR':'Calabria','LC':'Lombardia','LE':'Puglia',
    'LI':'Toscana','LO':'Lombardia','LT':'Lazio','LU':'Toscana',
    'MB':'Lombardia','MC':'Marche','ME':'Sicilia','MI':'Lombardia',
    'MN':'Lombardia','MO':'Emilia-Romagna','MS':'Toscana','MT':'Basilicata',
    'NA':'Campania','NO':'Piemonte','NU':'Sardegna','OR':'Sardegna',
    'PA':'Sicilia','PC':'Emilia-Romagna','PD':'Veneto','PE':'Abruzzo',
    'PG':'Umbria','PI':'Toscana','PN':'Friuli-Venezia Giulia',
    'PO':'Toscana','PR':'Emilia-Romagna','PT':'Toscana','PU':'Marche',
    'PV':'Lombardia','PZ':'Basilicata','RA':'Emilia-Romagna','RC':'Calabria',
    'RE':'Emilia-Romagna','RG':'Sicilia','RI':'Lazio','RM':'Lazio',
    'RN':'Emilia-Romagna','RO':'Veneto','SA':'Campania','SI':'Toscana',
    'SO':'Lombardia','SP':'Liguria','SR':'Sicilia','SS':'Sardegna',
    'SU':'Sardegna','SV':'Liguria','TA':'Puglia','TE':'Abruzzo',
    'TN':'Trentino-Alto Adige','TO':'Piemonte','TP':'Sicilia',
    'TR':'Umbria','TS':'Friuli-Venezia Giulia','TV':'Veneto',
    'UD':'Friuli-Venezia Giulia','VA':'Lombardia','VB':'Piemonte',
    'VC':'Piemonte','VE':'Veneto','VI':'Veneto','VR':'Veneto',
    'VS':'Sardegna','VT':'Lazio','VV':'Calabria',
}

# ─── Sorgenti ──────────────────────────────────────────────────────────────
SORGENTI = [
    'https://www.eventiesagre.it/Mercatini_Artigianato/elenco.html?mese=8&anno=2026',
    'https://www.eventiesagre.it/Mercatini_Artigianato/elenco.html?mese=9&anno=2026',
    'https://www.eventiesagre.it/Mercatini_Artigianato/elenco.html?mese=10&anno=2026',
    'https://www.unicofattoamano.it/candidatura-mercato/',
    'https://gipsygarden.it/open-call/',
    'https://lo-smanet.com/',
    'https://www.handmadestories.it/',
    'https://www.eventiesagre.it/Mercatini_Creativi/elenco.html?mese=9&anno=2026',
    'https://www.eventiesagre.it/Mercatini_Creativi/elenco.html?mese=10&anno=2026',
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; MercatiniBot/1.0; +https://mercatini.blog)',
    'Accept-Language': 'it-IT,it;q=0.9',
}

PROMPT_ESTRAI = """Sei un assistente che estrae informazioni strutturate su mercatini artigianali italiani da testo web.

Dalla pagina web fornita, estrai TUTTI gli eventi/mercatini che rientrano nel periodo {data_min} – {data_max}.
Includi solo eventi futuri o in corso. Escludi eventi già passati.

Per ogni evento restituisci un oggetto JSON con questi campi:
- titolo: nome dell'evento (string)
- citta: città (string)
- provincia: sigla provincia 2 lettere maiuscole o null
- data_inizio: data inizio formato YYYY-MM-DD o null se non chiara
- data_fine: data fine formato YYYY-MM-DD (uguale a data_inizio se evento di un giorno) o null
- orario: orario apertura es "9:00-19:00" o null
- indirizzo: indirizzo specifico o luogo (piazza, parco, ecc.) o null
- descrizione: breve descrizione 1-2 frasi o null
- sito_web: URL sito ufficiale o pagina evento o null
- email_contatto: email di contatto o null
- ingresso_gratuito: true/false (true se non indicato altrimenti)
- numero_espositori: numero stand/espositori se indicato (int) o null

Restituisci SOLO un array JSON valido, senza testo aggiuntivo, senza markdown.
Se non trovi nessun evento, restituisci [].
"""


def fetch_page(url):
    """Scarica una pagina e restituisce il testo pulito (max 12000 chars)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        # Rimuovi script, style, nav, footer
        for tag in soup(['script','style','nav','footer','head']):
            tag.decompose()
        text = soup.get_text(separator='\n', strip=True)
        # Comprimi righe vuote consecutive
        lines = [l for l in text.splitlines() if l.strip()]
        return '\n'.join(lines)[:12000]
    except Exception as e:
        log.warning(f'Errore fetch {url}: {e}')
        return None


def estrai_eventi_con_claude(testo, url):
    """Usa Claude Haiku per estrarre lista eventi strutturati dal testo."""
    client = anthropic.Anthropic()
    prompt = PROMPT_ESTRAI.format(
        data_min=OGGI.isoformat(),
        data_max=DATA_FINE_RICERCA.isoformat()
    )
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=2000,
            messages=[{
                'role': 'user',
                'content': f"{prompt}\n\nContenuto della pagina ({url}):\n\n{testo}"
            }]
        )
        raw = msg.content[0].text.strip()
        # Rimuovi backtick markdown se presenti
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1]
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        return json.loads(raw)
    except Exception as e:
        log.warning(f'Errore Claude per {url}: {e}')
        return []


def parse_data(s):
    """Converte stringa YYYY-MM-DD in date, o None."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def is_duplicato(titolo, citta, data_inizio):
    """Controlla se esiste già un mercatino con stesso titolo+città+data."""
    if not data_inizio:
        return False
    existing = Mercatino.query.filter(
        db.func.lower(Mercatino.titolo) == titolo.lower(),
        db.func.lower(Mercatino.citta) == citta.lower(),
        Mercatino.data_inizio == data_inizio,
    ).first()
    return existing is not None


def inserisci_bozza(ev, fonte_url, cat_artigianato):
    """Inserisce un evento come bozza nel DB. Restituisce True se inserito."""
    titolo = (ev.get('titolo') or '').strip()
    citta  = (ev.get('citta') or '').strip()
    if not titolo or not citta:
        log.debug(f'Skip evento senza titolo/città: {ev}')
        return False

    data_inizio = parse_data(ev.get('data_inizio'))
    data_fine   = parse_data(ev.get('data_fine')) or data_inizio
    if not data_inizio:
        log.debug(f'Skip "{titolo}" – data_inizio mancante')
        return False
    if data_inizio < OGGI or data_inizio > DATA_FINE_RICERCA:
        log.debug(f'Skip "{titolo}" – fuori finestra: {data_inizio}')
        return False
    if is_duplicato(titolo, citta, data_inizio):
        log.info(f'Duplicato: "{titolo}" a {citta} ({data_inizio})')
        return False

    prov = (ev.get('provincia') or '').upper().strip() or None
    regione = PROV_REGIONE.get(prov, 'Italia') if prov else 'Italia'

    m = Mercatino(
        titolo            = titolo[:200],
        citta             = citta[:100],
        regione           = regione[:100],
        provincia         = prov,
        indirizzo         = (ev.get('indirizzo') or '')[:255] or None,
        descrizione       = ev.get('descrizione') or None,
        data_inizio       = data_inizio,
        data_fine         = data_fine,
        orario            = (ev.get('orario') or '')[:100] or None,
        sito_web          = (ev.get('sito_web') or '')[:500] or None,
        email_contatto    = (ev.get('email_contatto') or '')[:255] or None,
        ingresso_gratuito = bool(ev.get('ingresso_gratuito', True)),
        numero_espositori = ev.get('numero_espositori') or None,
        pubblicato        = False,
        fonte_crawler     = fonte_url[:500],
        organizzatore_id  = ADMIN_USER_ID,
    )
    if cat_artigianato:
        m.categorie.append(cat_artigianato)
    db.session.add(m)
    return True


def run():
    app = create_app()
    with app.app_context():
        cat_artigianato = db.session.get(Categoria, CAT_ARTIGIANATO_ID)
        totale_inseriti = 0
        totale_trovati  = 0

        for url in SORGENTI:
            log.info(f'Scansione: {url}')
            testo = fetch_page(url)
            if not testo:
                continue

            eventi = estrai_eventi_con_claude(testo, url)
            log.info(f'  Claude ha estratto {len(eventi)} eventi da {url}')
            totale_trovati += len(eventi)

            inseriti_url = 0
            for ev in eventi:
                try:
                    if inserisci_bozza(ev, url, cat_artigianato):
                        inseriti_url += 1
                except Exception as e:
                    log.error(f'  Errore inserimento "{ev.get("titolo","?")}" : {e}')

            if inseriti_url:
                db.session.commit()
                log.info(f'  Inserite {inseriti_url} bozze da {url}')
            totale_inseriti += inseriti_url

        log.info(
            f'CRAWLER COMPLETATO — trovati {totale_trovati}, '
            f'inserite {totale_inseriti} nuove bozze'
        )


if __name__ == '__main__':
    run()
