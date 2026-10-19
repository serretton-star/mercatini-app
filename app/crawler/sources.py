"""
app/crawler/sources.py
Sorgenti dati: DuckDuckGo web, Facebook pubblico, Instagram pubblico.
Restituisce liste di dict con campi grezzi da normalizzare.
"""
import logging
import re
import time
import random
from typing import List, Dict, Optional
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

REGIONI_IT = [
    "Lombardia", "Veneto", "Lazio", "Campania", "Sicilia", "Piemonte",
    "Emilia-Romagna", "Toscana", "Puglia", "Calabria", "Sardegna",
    "Liguria", "Marche", "Abruzzo", "Friuli-Venezia Giulia", "Umbria",
    "Trentino-Alto Adige", "Basilicata", "Molise", "Valle d'Aosta",
]


def _sleep():
    time.sleep(random.uniform(1.2, 2.5))


# ---------------------------------------------------------------------------
# 1. DuckDuckGo / web search
# ---------------------------------------------------------------------------

def cerca_ddg(query: str, max_results: int = 10) -> List[Dict]:
    """Cerca tramite DuckDuckGo e ritorna risultati con url + snippet."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, region='it-it', max_results=max_results):
                results.append({
                    'url': r.get('href', ''),
                    'titolo': r.get('title', ''),
                    'snippet': r.get('body', ''),
                    'fonte': 'web_ddg',
                })
        return results
    except Exception as e:
        log.warning(f'[ddg] Errore: {e}')
        return []


def scrapa_pagina(url: str, timeout: int = 10) -> str:
    """Scarica e ritorna il testo pulito di una pagina web."""
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        # Rimuovi nav, footer, script, style
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            tag.decompose()
        return soup.get_text(separator=' ', strip=True)[:8000]
    except Exception as e:
        log.debug(f'[scrape] {url}: {e}')
        return ''


def query_mercatini_web(mese: int, anno: int) -> List[Dict]:
    """
    Genera query per il mese/anno e cerca su DuckDuckGo.
    Copre le 20 regioni italiane.
    """
    from .parser import MESI_IT
    nome_mese = {v: k for k, v in MESI_IT.items() if len(k) > 4}.get(mese, str(mese))
    results = []

    # Query generiche
    queries = [
        f'mercatini artigianali {nome_mese} {anno} italia',
        f'fiera hobbisti {nome_mese} {anno}',
        f'mercatino antiquariato {nome_mese} {anno}',
    ]
    # Query per regione
    for regione in REGIONI_IT[:10]:  # prime 10 per non esagerare
        queries.append(f'mercatini {nome_mese} {anno} {regione}')

    seen_urls = set()
    for q in queries:
        for r in cerca_ddg(q, max_results=8):
            if r['url'] and r['url'] not in seen_urls:
                seen_urls.add(r['url'])
                results.append(r)
        _sleep()

    log.info(f'[web] {len(results)} URL trovati per {nome_mese} {anno}')
    return results


# ---------------------------------------------------------------------------
# 2. Facebook pagine pubbliche
# ---------------------------------------------------------------------------

def cerca_facebook_events(query: str) -> List[Dict]:
    """
    Cerca eventi pubblici Facebook tramite DuckDuckGo site:facebook.com.
    Non richiede login.
    """
    results = []
    q = f'site:facebook.com mercatino {query} -login -register'
    for r in cerca_ddg(q, max_results=15):
        url = r.get('url', '')
        # Filtra solo pagine eventi/pagine pubbliche
        if 'facebook.com' in url and '/events/' in url:
            results.append({**r, 'fonte': 'facebook'})
    return results


def scrapa_facebook_event(url: str) -> str:
    """Tenta di recuperare il testo pubblico di un evento FB (mobile)."""
    # Usa versione mobile che spesso non richiede login per eventi pubblici
    url_mobile = url.replace('www.facebook.com', 'm.facebook.com')
    testo = scrapa_pagina(url_mobile)
    if not testo or 'log in' in testo.lower()[:200]:
        return ''
    return testo


def query_facebook(mese: int, anno: int) -> List[Dict]:
    from .parser import MESI_IT
    nome_mese = {v: k for k, v in MESI_IT.items() if len(k) > 4}.get(mese, str(mese))
    results = []
    queries = [
        f'{nome_mese} {anno}',
        f'artigiani {nome_mese} {anno}',
        f'hobbisti {nome_mese} {anno}',
    ]
    seen = set()
    for q in queries:
        for r in cerca_facebook_events(q):
            if r['url'] not in seen:
                seen.add(r['url'])
                results.append(r)
        _sleep()
    log.info(f'[facebook] {len(results)} eventi trovati')
    return results


# ---------------------------------------------------------------------------
# 3. Instagram pubblico (instaloader)
# ---------------------------------------------------------------------------

HASHTAG_MERCATINI = [
    'mercatiniartigianali', 'mercatinoartigianale', 'fieraartigianale',
    'mercatino', 'artigianatoitaliano', 'hobbisti', 'handmadeitaly',
    'mercatinivintage', 'antiquariato', 'fierahobbisti',
]

IG_ACCOUNTS_NOTI = [
    # Aggiungere account noti nel tempo
]


def query_instagram(mese: int, anno: int, max_post_per_tag: int = 30) -> List[Dict]:
    """
    Scarica post pubblici da hashtag Instagram tramite instaloader (senza login).
    Ritorna testo grezzo dei post che sembrano mercatini.
    """
    results = []
    try:
        import instaloader
        L = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            quiet=True,
        )

        from .parser import testo_e_mercatino
        anno_str = str(anno)

        for hashtag in HASHTAG_MERCATINI[:5]:  # Limita per velocità
            try:
                posts = instaloader.Hashtag.from_name(L.context, hashtag).get_posts()
                count = 0
                for post in posts:
                    if count >= max_post_per_tag:
                        break
                    caption = post.caption or ''
                    # Filtra per anno/mese e pertinenza
                    if anno_str in caption and testo_e_mercatino(caption):
                        results.append({
                            'url': f'https://www.instagram.com/p/{post.shortcode}/',
                            'titolo': caption[:80].strip().replace('\n', ' '),
                            'snippet': caption[:500],
                            'testo_completo': caption,
                            'fonte': 'instagram',
                            'data_post': post.date.date() if post.date else None,
                        })
                    count += 1
                _sleep()
            except Exception as e:
                log.debug(f'[ig] hashtag #{hashtag}: {e}')

    except ImportError:
        log.warning('[ig] instaloader non installato, skip Instagram')
    except Exception as e:
        log.warning(f'[ig] Errore generale: {e}')

    log.info(f'[instagram] {len(results)} post rilevanti')
    return results


# ---------------------------------------------------------------------------
# Aggregatore
# ---------------------------------------------------------------------------

def raccogli_tutte_le_fonti(mese: int, anno: int) -> List[Dict]:
    """Raccoglie risultati grezzi da tutte le fonti."""
    tutto = []
    tutto.extend(query_mercatini_web(mese, anno))
    tutto.extend(query_facebook(mese, anno))
    tutto.extend(query_instagram(mese, anno))
    log.info(f'[crawler] Totale grezzo: {len(tutto)} risultati')
    return tutto
