#!/bin/bash
cd /var/www/mercatini
source /var/www/mercatini/venv/bin/activate
python /var/www/mercatini/scripts/invia_alert.py >> /var/www/mercatini/logs/alert_cron.log 2>&1
