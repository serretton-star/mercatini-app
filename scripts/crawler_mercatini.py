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
    # eventiesagre.it – artigianato per mese
    'https://www.eventiesagre.it/Mercatini_Artigianato/elenco.html?mese=8&anno=2026',
    'https://www.eventiesagre.it/Mercatini_Artigianato/elenco.html?mese=9&anno=2026',
    'https://www.eventiesagre.it/Mercatini_Artigianato/elenco.html?mese=10&anno=2026',
    # eventiesagre.it – altre categorie
    'https://www.eventiesagre.it/Fiere_Artigianato/elenco.html?mese=9&anno=2026',
    'https://www.eventiesagre.it/Fiere_Artigianato/elenco.html?mese=10&anno=2026',
    'https://www.eventiesagre.it/Mercatini/elenco.html?mese=9&anno=2026',
    'https://www.eventiesagre.it/Mercatini/elenco.html?mese=10&anno=2026',
    # organizzatori con open call
    'https://lo-smanet.com/',
    'https://wemakeapair.com/',
    'https://www.mercatinobiologico.it/',
    # portali aggregatori
    'https://www.fiere.it/mercatini-artigianato.asp',
    'https://www.italyguides.it/it/eventi/mercatini-artigianato',
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
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
    """
    True se esiste gia' un mercatino simile nel DB.
    Check 1: titolo esatto + citta + data_inizio (case-insensitive)
    Check 2: stessa citta + stessa data + almeno 2 parole chiave in comune nel titolo
    """
    if not data_inizio or not citta:
        return False
    citta_n  = citta.lower().strip()
    titolo_n = titolo.lower().strip()

    # Check 1: match esatto
    if Mercatino.query.filter(
        db.func.lower(Mercatino.titolo) == titolo_n,
        db.func.lower(Mercatino.citta)  == citta_n,
        Mercatino.data_inizio == data_inizio,
    ).first():
        return True

    # Check 2: stessa citta + stessa data_inizio, titolo simile
    candidati = Mercatino.query.filter(
        db.func.lower(Mercatino.citta) == citta_n,
        Mercatino.data_inizio == data_inizio,
    ).all()
    if candidati:
        parole_nuove = {p for p in titolo_n.split() if len(p) >= 4}
        for cand in candidati:
            parole_old = {p for p in cand.titolo.lower().split() if len(p) >= 4}
            if len(parole_nuove & parole_old) >= 2:
                log.info(f'Duplicato fuzzy: "{titolo}" ~ "{cand.titolo}" a {citta} ({data_inizio})')
                return True

    return False


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

        # Promo-D.com
        crawla_promod(cat_artigianato, log)
        log.info(
            f'CRAWLER COMPLETATO — trovati {totale_trovati}, '
            f'inserite {totale_inseriti} nuove bozze'
        )



# ──────────────────────────────────────────────────────────
# PROMO-D.COM – scraper dedicato (struttura server-rendered)
# ──────────────────────────────────────────────────────────
MESI_IT = {
    'gennaio':1,'febbraio':2,'marzo':3,'aprile':4,'maggio':5,'giugno':6,
    'luglio':7,'agosto':8,'settembre':9,'ottobre':10,'novembre':11,'dicembre':12,
    'gen':1,'feb':2,'mar':3,'apr':4,'mag':5,'giu':6,
    'lug':7,'ago':8,'set':9,'ott':10,'nov':11,'dic':12,
}

def _parse_data_it(s):
    """Converte '31 Maggio 2026' / '09 Set 2026' in date."""
    from datetime import date
    parts = s.strip().split()
    if len(parts) < 3:
        return None
    try:
        g = int(parts[0])
        m = MESI_IT.get(parts[1].lower())
        a = int(parts[2])
        return date(a, m, g) if m else None
    except Exception:
        return None


def _fetch_promod_slugs():
    """Raccoglie tutti gli slug /evento/ dalle pagine listing di promo-d.com."""
    import re
    listing_urls = [
        'https://www.promo-d.com/mercatini/',
        'https://www.promo-d.com/eventi-in-programma/',
        'https://www.promo-d.com/fiere/',
        'https://www.promo-d.com/antiquariato/',
    ]
    seen = set()
    for url in listing_urls:
        try:
            # Usa requests direttamente per cercare href nel HTML grezzo
            resp = requests.get(url, headers=HEADERS, timeout=15)
            found = re.findall('/evento/([\w-]+)/', resp.text)
            for slug in found:
                seen.add(slug)
        except Exception as e:
            pass  # log silenzioso
    return list(seen)


def _parse_promod_evento(url):
    """Estrae dati strutturati da una singola pagina evento promo-d.com."""
    from bs4 import BeautifulSoup
    import re
    try:
        html = requests.get(url, headers=HEADERS, timeout=15).text
    except Exception as e:
        log.warning(f"promo-d evento {url}: {e}")
        return None
    soup = BeautifulSoup(html, 'html.parser')
    # Titolo
    h1 = soup.find('h1')
    titolo = h1.get_text(strip=True) if h1 else None
    if not titolo:
        return None
    # Testo completo per estrarre campi
    testo = soup.get_text(separator=' ')
    def find_field(label):
        m = re.search(label + r'\s+([\w\s]+?(?:\d{4}))', testo, re.IGNORECASE)
        return m.group(1).strip() if m else None
    data_ini_str = find_field('Data inizio')
    data_fin_str = find_field('Data fine')
    data_ini = _parse_data_it(data_ini_str) if data_ini_str else None
    data_fin = _parse_data_it(data_fin_str) if data_fin_str else data_ini
    # Località
    loc_m = re.search(r'Localit[àa]\s+([^\n]{3,60})', testo)
    citta = loc_m.group(1).strip() if loc_m else None
    # Orari
    or_m = re.search(r'(dalle?\s+\d+[:\.]\d+.{0,50})', testo, re.IGNORECASE)
    orario = or_m.group(1).strip()[:100] if or_m else None
    # Descrizione (primo blocco di testo utile)
    desc_m = re.search(r'(?:Localit[àa]\s+[^\n]+\n)([\s\S]{50,600}?)(?:Sei un espositore|Per ulteriori|Documenti)', testo)
    descrizione = re.sub(r'\s+', ' ', desc_m.group(1)).strip()[:800] if desc_m else titolo
    return {
        'titolo': titolo,
        'citta': citta,
        'data_inizio': data_ini,
        'data_fine': data_fin,
        'orario': orario,
        'descrizione': descrizione,
        'sito_web': url,
        'provincia': None,
        'regione': None,
        'indirizzo': None,
    }


def crawla_promod(cat_artigianato, logger=None):
    """Scraper dedicato per promo-d.com"""
    import logging as _logging
    if logger is None:
        logger = _logging.getLogger(__name__)
    from datetime import date
    oggi = date.today()
    logger.info("=== promo-d.com: inizio ===")
    slugs = _fetch_promod_slugs()
    logger.info(f"promo-d: {len(slugs)} eventi trovati")
    inseriti = 0
    for slug in slugs:
        url = f"https://www.promo-d.com/evento/{slug}/"
        ev = _parse_promod_evento(url)
        if not ev:
            continue
        # Scarta solo se sia data_inizio sia data_fine sono nel passato
        data_fine_ev = ev.get('data_fine') or ev['data_inizio']
        if not ev['data_inizio'] or data_fine_ev < oggi:
            continue
        if is_duplicato(ev['titolo'], ev['citta'] or '', ev['data_inizio']):
            logger.info(f"  dup: {ev['titolo']}")
            continue
        inserisci_bozza(ev, url, cat_artigianato)
        inseriti += 1
        logger.info(f"  + {ev['titolo']} ({ev['citta']})")
    logger.info(f"promo-d.com: {inseriti} nuovi inseriti")

if __name__ == '__main__':
    run()
