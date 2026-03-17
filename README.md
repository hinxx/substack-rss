# Substack RSS Summarizer

A Python-based, AI-powered application that automatically fetches Substack RSS feeds, reads the articles, generates tailored summaries using local LLMs (via [Ollama](https://ollama.com/)), and serves them in an easy-to-read web interface using [Flask](https://flask.palletsprojects.com/).

## Features

- **Automated Fetching**: Runs a background daemon thread that periodically checks for new articles across all your subscribed feeds every 3 hours.
- **Dynamic AI Meta-Prompting**: Evaluates the title and description of a new feed to automatically write a custom instructions prompt for the AI, adopting the perfect persona (e.g., financial analyst, tech reviewer) for that specific publication.
- **Local & Cloud AI Support**: Uses a local Ollama model (`llama3.1:8b`) by default to ensure privacy and avoid API costs. (Alternative script versions support Google Gemini via API).
- **Smart Parsing**: Cleans and strips HTML tags using BeautifulSoup, and truncates overly long articles to safely fit within the LLM's context window.
- **Web Interface**: A sleek, tabbed Flask web UI that renders generated summaries as Markdown. Features include:
  - Read summaries sorted by reverse chronological order.
  - **System Prompts Tab**: View and tweak the AI instructions generated for each individual feed.
  - **Add Feed**: Subscribe to new Substack feeds on the fly directly from the UI.
  - **Refresh Now**: Manually trigger an immediate sync of all feeds.
- **Persistent Storage**: Safely tracks downloaded articles, summaries, and feed configurations using a local SQLite database (`summaries.db`).

## Prerequisites

- **Python 3.8+**
- **Ollama**: Must be installed and running locally. Download Ollama

## Installation

1. **Clone the repository** (or download the files to your machine):
   ```bash
   git clone <your-repo-url>
   cd substack-rss
   ```

2. **Set up a Virtual Environment** (Recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```

3. **Install Python Dependencies**:
   ```bash
   pip install feedparser ollama flask beautifulsoup4
   ```

4. **Pull the Ollama Model**:
   Make sure the default model is downloaded to your local Ollama instance:
   ```bash
   ollama pull llama3.1:8b
   ```

## Usage

1. **Start the application**:
   ```bash
   python parse-rss-1.py
   ```

2. **Open the Web UI**:
   Navigate to http://localhost:5001 in your web browser.

3. **First Boot**:
   On the very first run, the app will automatically seed the database with a default list of financial Substack feeds, fetch their latest articles, and begin generating summaries. This might take a few moments depending on your local hardware.

## How it Works

1. **Initialization**: The script connects to `summaries.db`. If empty, it provisions the required tables (`articles`, `feed_prompts`, `feeds`).
2. **Background Fetcher**: A detached background thread wakes up every 3 hours. It retrieves URLs from the `feeds` table and fetches the RSS XML.
3. **Processing**:
   - Checks if the article URL already exists in the database.
   - Uses `BeautifulSoup` to extract raw text from the Substack HTML payload.
   - Truncates text up to a safe 60,000 character limit.
   - Invokes Ollama to generate a summary based on the feed's custom system prompt.
4. **Serving**: The Flask web server dynamically reads from the SQLite database and renders the records via an HTML template using `marked.js` for Markdown styling.

## Troubleshooting

- **`Error invoking Ollama`**: Ensure the Ollama app is running in the background and that you have pulled the requested model.
- **Missing Modules**: Ensure your virtual environment is active and all packages listed in the Installation step are fully installed.
- **Database Issues**: If the application crashes due to schema errors, you can safely delete the `summaries.db` file to let the script rebuild a fresh one on the next launch.