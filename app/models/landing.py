import hashlib
from datetime import datetime, timezone
from app import db


class LandingVisit(db.Model):
    __tablename__ = 'landing_visits'
    id          = db.Column(db.Integer, primary_key=True)
    timestamp   = db.Column(db.DateTime(timezone=True), nullable=False,
                            default=lambda: datetime.now(timezone.utc), index=True)
    ip_hash     = db.Column(db.String(64),  nullable=True, index=True)
    referrer    = db.Column(db.String(500), nullable=True)
    user_agent  = db.Column(db.String(300), nullable=True)

    @staticmethod
    def log_visit(request):
        ip = (request.headers.get('X-Forwarded-For', '') or request.remote_addr or '')
        ip = ip.split(',')[0].strip()
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:32] if ip else None
        ref = (request.referrer or '')[:500]
        ua  = (request.user_agent.string or '')[:300]
        v = LandingVisit(ip_hash=ip_hash, referrer=ref, user_agent=ua)
        db.session.add(v)
        db.session.commit()
