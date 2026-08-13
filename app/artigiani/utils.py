"""
app/artigiani/utils.py
Utility: compressione foto, gestione storage, helpers sessione hobbista.
"""
import os
import uuid
import logging
from functools import wraps

from flask import session, redirect, url_for, current_app, request

log = logging.getLogger(__name__)

# ── Costanti ──────────────────────────────────────────────────────────────────
MAX_SIDE    = 1600          # px lato lungo full
THUMB_SIDE  = 400           # px lato lungo thumbnail
JPEG_Q      = 82            # qualità JPEG
MAX_FILE_MB = 8             # limite upload singolo file
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp'}


# ── Session helpers ───────────────────────────────────────────────────────────

def get_current_hobbista():
    """Restituisce l'HobbistaAccount dalla sessione, o None."""
    hid = session.get('hobbista_id')
    if not hid:
        return None
    from app.models.hobbisti import HobbistaAccount
    return HobbistaAccount.query.get(hid)


def hobbista_required(f):
    """Decorator: richiede login hobbista (session-based, separato da Flask-Login)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('hobbista_id'):
            return redirect(url_for('artigiani_auth.login',
                                    next=request.full_path))
        return f(*args, **kwargs)
    return decorated


# ── Percorsi upload ───────────────────────────────────────────────────────────

def _upload_base():
    return current_app.config['ARTIGIANI_UPLOAD_FOLDER']


def _static_rel():
    """Path relativo alla cartella static/ (usato in HobbistaFoto.path_relativo)."""
    return current_app.config.get('ARTIGIANI_UPLOAD_STATIC_REL', 'uploads/artigiani')


def _account_dir(account_id, thumb=False):
    base = os.path.join(_upload_base(), str(account_id))
    d = os.path.join(base, 'thumb') if thumb else base
    os.makedirs(d, exist_ok=True)
    return d


# ── Validazione ───────────────────────────────────────────────────────────────

def allowed_file(filename):
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT)


# ── Compressione e salvataggio ────────────────────────────────────────────────

def salva_foto(fileobj, account_id):
    """
    Riceve un file-like object (da request.files), lo comprime e salva.
    Restituisce (path_relativo, filename, dimensione_kb) o lancia ValueError.

    path_relativo è relativo a app/static/, es:
        uploads/artigiani/7/abc123.jpg
    """
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("Pillow non installato. Aggiungi 'Pillow' a requirements.txt")

    safe_name = f"{uuid.uuid4().hex}.jpg"

    # ── Full size ──────────────────────────────────────────────────────────────
    img = Image.open(fileobj)
    img = img.convert('RGB')   # gestisce PNG con alpha, WEBP, ecc.

    w, h = img.size
    if max(w, h) > MAX_SIDE:
        if w >= h:
            img = img.resize((MAX_SIDE, int(h * MAX_SIDE / w)), Image.LANCZOS)
        else:
            img = img.resize((int(w * MAX_SIDE / h), MAX_SIDE), Image.LANCZOS)

    full_dir  = _account_dir(account_id)
    full_path = os.path.join(full_dir, safe_name)
    img.save(full_path, 'JPEG', quality=JPEG_Q, optimize=True)

    # ── Thumbnail ──────────────────────────────────────────────────────────────
    img_t = img.copy()
    tw, th = img_t.size
    if max(tw, th) > THUMB_SIDE:
        if tw >= th:
            img_t = img_t.resize((THUMB_SIDE, int(th * THUMB_SIDE / tw)), Image.LANCZOS)
        else:
            img_t = img_t.resize((int(tw * THUMB_SIDE / th), THUMB_SIDE), Image.LANCZOS)

    thumb_dir  = _account_dir(account_id, thumb=True)
    thumb_path = os.path.join(thumb_dir, safe_name)
    img_t.save(thumb_path, 'JPEG', quality=JPEG_Q, optimize=True)

    # ── Risultato ──────────────────────────────────────────────────────────────
    size_kb      = (os.path.getsize(full_path) + os.path.getsize(thumb_path)) // 1024
    path_relativo = f"{_static_rel()}/{account_id}/{safe_name}"

    return path_relativo, safe_name, size_kb


def elimina_foto_files(foto):
    """Elimina i file fisici (full + thumb) di una HobbistaFoto."""
    try:
        base  = _upload_base()
        full  = os.path.join(base, str(foto.account_id), foto.filename)
        thumb = os.path.join(base, str(foto.account_id), 'thumb', foto.filename)
        for p in (full, thumb):
            if os.path.isfile(p):
                os.remove(p)
    except Exception as e:
        log.warning(f"Errore eliminazione file foto {foto.id}: {e}")


def ricalcola_storage(account_id):
    """
    Ricalcola storage_usato_mb dal filesystem reale e aggiorna l'account.
    Chiamare dopo ogni upload e dopo ogni delete.
    """
    from app import db
    from app.models.hobbisti import HobbistaAccount

    account_dir = os.path.join(_upload_base(), str(account_id))
    total_bytes = 0
    if os.path.isdir(account_dir):
        for root, _dirs, files in os.walk(account_dir):
            for fname in files:
                try:
                    total_bytes += os.path.getsize(os.path.join(root, fname))
                except OSError:
                    pass

    acc = db.session.get(HobbistaAccount, account_id)
    if acc:
        acc.storage_usato_mb = round(total_bytes / (1024 * 1024), 3)
        db.session.commit()
    return acc.storage_usato_mb if acc else 0.0
