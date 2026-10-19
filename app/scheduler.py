"""
app/scheduler.py
APScheduler — job periodici del progetto mercatini.blog.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)
_scheduler = BackgroundScheduler(daemon=True, timezone='Europe/Rome')


def init_scheduler(app):
    """Inizializza e avvia APScheduler con i job configurati."""
    from app.tasks import invia_digest_foto_hobbisti
    from app.crawler.run import esegui_crawler_schedulato

    ora = int(app.config.get('DIGEST_ORA_FOTO', 18))

    _scheduler.add_job(
        func=lambda: invia_digest_foto_hobbisti(app),
        trigger=CronTrigger(hour=ora, minute=0),
        id='digest_foto_hobbisti',
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Crawler mercatini: ogni lunedì alle 04:00 (Europe/Rome)
    _scheduler.add_job(
        func=lambda: esegui_crawler_schedulato(app),
        trigger=CronTrigger(day_of_week='mon', hour=4, minute=0),
        id='crawler_mercatini',
        replace_existing=True,
        misfire_grace_time=7200,
    )

    if not _scheduler.running:
        _scheduler.start()
        log.info(
            f'[scheduler] Avviato. Digest foto: ogni giorno alle {ora:02d}:00. '
            f'Crawler: ogni lunedì alle 04:00 (Europe/Rome).'
        )
