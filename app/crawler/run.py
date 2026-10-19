"""
app/crawler/run.py
Entry point del crawler — Flask CLI command e funzione richiamabile da scheduler.

Uso:
    flask crawler run                          # mese corrente
    flask crawler run --mese 11 --anno 2025   # mese specifico
    flask crawler run --mesi-avanti 3         # prossimi 3 mesi
"""
import logging
from datetime import date, timedelta
from typing import List, Tuple

import click

log = logging.getLogger(__name__)


def _run_crawler(app, mese: int, anno: int) -> Tuple[int, int]:
    """Esegue il crawler per un mese/anno specifico. Ritorna (salvati, saltati)."""
    with app.app_context():
        from .sources import raccogli_tutte_le_fonti, scrapa_pagina
        from .parser import testo_e_mercatino
        from .importer import normalizza, salva_nel_db, ottieni_bot_user_id

        bot_id = ottieni_bot_user_id(app)
        if not bot_id:
            log.error('[crawler] Impossibile determinare bot_user_id. Abort.')
            return 0, 0

        log.info(f'[crawler] Avvio per {mese:02d}/{anno} (bot_user_id={bot_id})')

        # 1. Raccogli risultati grezzi
        grezzi = raccogli_tutte_le_fonti(mese, anno)

        # 2. Arricchisci con testo pagina per risultati web
        arricchiti = []
        for r in grezzi:
            testo_pag = ''
            if r.get('fonte') in ('web_ddg',) and r.get('url'):
                testo_pag = scrapa_pagina(r['url'])
            arricchiti.append((r, testo_pag))

        # 3. Normalizza
        normalizzati = []
        for raw, testo_pag in arricchiti:
            n = normalizza(raw, testo_pag)
            if n:
                normalizzati.append(n)

        log.info(f'[crawler] {len(normalizzati)} eventi normalizzati su {len(grezzi)} grezzi')

        # 4. Salva nel DB
        salvati, saltati = salva_nel_db(normalizzati, bot_id)
        log.info(f'[crawler] Salvati: {salvati}, Saltati (già presenti): {saltati}')
        return salvati, saltati


def registra_comandi(app):
    """Registra i comandi Flask CLI del crawler."""

    @app.cli.group('crawler')
    def crawler_group():
        """Comandi per il crawler di mercatini."""
        pass

    @crawler_group.command('run')
    @click.option('--mese', default=None, type=int,
                  help='Mese da cercare (1-12). Default: mese corrente.')
    @click.option('--anno', default=None, type=int,
                  help='Anno da cercare. Default: anno corrente.')
    @click.option('--mesi-avanti', default=1, type=int,
                  help='Quanti mesi avanti cercare (incluso il corrente). Default: 1.')
    def cmd_run(mese, anno, mesi_avanti):
        """Cerca e importa mercatini da web, Facebook e Instagram."""
        oggi = date.today()
        if not mese:
            mese = oggi.month
        if not anno:
            anno = oggi.year

        totale_salvati = 0
        totale_saltati = 0

        start = date(anno, mese, 1)
        for i in range(mesi_avanti):
            # Calcola mese i-esimo avanti
            m = start.month + i
            a = start.year + (m - 1) // 12
            m = ((m - 1) % 12) + 1

            click.echo(f'🔍 Cercando mercatini per {m:02d}/{a}...')
            s, sk = _run_crawler(app, m, a)
            totale_salvati += s
            totale_saltati += sk

        click.echo(
            f'\n✅ Completato! Salvati: {totale_salvati} bozze, '
            f'già presenti: {totale_saltati}.'
        )
        if totale_salvati > 0:
            click.echo('   → Vai su /admin/mercatini per verificare e pubblicare le bozze.')

    @crawler_group.command('status')
    def cmd_status():
        """Mostra statistiche sulle bozze in attesa di revisione."""
        with app.app_context():
            from app import db
            from app.models.mercatino import Mercatino
            bozze = Mercatino.query.filter_by(pubblicato=False).count()
            pubblicati = Mercatino.query.filter_by(pubblicato=True).count()
            crawler_bozze = (
                Mercatino.query
                .filter_by(pubblicato=False)
                .filter(Mercatino.fonte_crawler.isnot(None))
                .count()
            )
            click.echo(f'📊 Stato database:')
            click.echo(f'   Pubblicati:          {pubblicati}')
            click.echo(f'   Bozze totali:        {bozze}')
            click.echo(f'   Di cui da crawler:   {crawler_bozze}')


def esegui_crawler_schedulato(app):
    """
    Funzione chiamata dallo scheduler APScheduler.
    Cerca mercatini per il mese corrente e il prossimo.
    """
    oggi = date.today()
    log.info('[scheduler] Avvio crawler schedulato')
    try:
        _run_crawler(app, oggi.month, oggi.year)
        # Cerca anche il mese prossimo
        prossimo = oggi.replace(day=1) + timedelta(days=32)
        _run_crawler(app, prossimo.month, prossimo.year)
    except Exception as e:
        log.error(f'[scheduler] Errore crawler schedulato: {e}')
