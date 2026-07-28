#!/bin/bash
set -e
cd /var/www/mercatini
source venv/bin/activate
python scripts/crawler_mercatini.py >> logs/crawler.log 2>&1
