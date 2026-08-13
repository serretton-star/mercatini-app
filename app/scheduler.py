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

    ora = int(app.config.get('DIGEST_ORA_FOTO', 18))

    _scheduler.add_job(
        func=lambda: invia_digest_foto_hobbisti(app),
        trigger=CronTrigger(hour=ora, minute=0),
        id='digest_foto_hobbisti',
        replace_existing=True,
        misfire_grace_time=3600,
    )

    if not _scheduler.running:
        _scheduler.start()
        log.info(
            f'[scheduler] Avviato. Digest foto: ogni giorno alle {ora:02d}:00 (Europe/Rome).'
        )
