#!/bin/bash
set -e

# 0. Restore the latest articles.json from the gh-pages branch if it's missing locally
mkdir -p data
if [ ! -s data/articles.json ]; then
    git fetch origin gh-pages 2>/dev/null || true
    if git rev-parse origin/gh-pages:data/articles.json >/dev/null 2>&1; then
        git show origin/gh-pages:data/articles.json > data/articles.json
        echo "Restored articles.json from origin/gh-pages"
    elif git rev-parse gh-pages:data/articles.json >/dev/null 2>&1; then
        git show gh-pages:data/articles.json > data/articles.json
        echo "Restored articles.json from local gh-pages"
    else
        echo "[]" > data/articles.json
    fi
fi

# 1. Run the headless python worker to fetch/summarize/generate static template
python worker.py

# Save any newly generated AI system prompts back to the master branch
git add feeds.json
git commit -m "Update feeds.json: $(date +'%Y-%m-%d %H:%M:%S')" || true
git push origin master

# 2. Copy the generated files to a temporary directory to avoid checkout conflicts
mkdir -p .tmp_deploy
cp data/articles.json .tmp_deploy/
cp index.html .tmp_deploy/

# 3. Create a temporary orphan branch for a clean history (no exploding git log)
git checkout --orphan temp-gh-pages
git rm -rf . || true

# 4. Restore the updated files into the working tree
mkdir -p data
cp .tmp_deploy/articles.json data/
cp .tmp_deploy/index.html .

# 5. Force add and commit, then force push to gh-pages branch
git add -f data/articles.json index.html
git commit -m "Worker Update: $(date +'%Y-%m-%d %H:%M:%S')"
git push -f origin temp-gh-pages:gh-pages

# 6. Return to master, delete the temporary branch, and restore the data files locally
git checkout -f master
git branch -D temp-gh-pages

mkdir -p data
cp .tmp_deploy/articles.json data/
cp .tmp_deploy/index.html .
rm -rf .tmp_deploy
