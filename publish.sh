#!/bin/bash
set -e

# 1. Run the headless python worker to fetch/summarize/generate static template
python worker.py

# 2. Git operations to publish statically generated output to gh-pages branch
git checkout gh-pages
git add data/articles.json data/feeds.json index.html
git commit -m "Worker Update: $(date +'%Y-%m-%d %H:%M:%S')" || echo "No changes to commit"
git push origin gh-pages

git checkout main