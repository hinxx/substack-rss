# Substack RSS Summarizer

A Python-based, AI-powered application that automatically fetches Substack RSS feeds, reads the articles, generates tailored summaries using local LLMs (via [Ollama](https://ollama.com/)) or Google Gemini, and builds a statically generated web interface. The site is designed to be easily deployed via GitHub Pages using a GitOps workflow.

## Features

- **Static Site Generation**: Compiles summaries into a lightning-fast, host-anywhere `index.html` using Jinja2 templating.
- **GitOps Deployment**: Includes a built-in `publish.sh` orchestration script and a GitHub Actions workflow to automate building and pushing to the `gh-pages` branch.
- **Dynamic AI Meta-Prompting**: Evaluates the title and description of a new feed to automatically write a custom system prompt, adopting the perfect persona for that specific publication.
- **Local & Cloud AI Support**: Uses a local Ollama model (`llama3.1:8b`) by default, with automatic fallback to Google Gemini (`gemini-2.5-flash`) if an API key is provided.
- **Smart Parsing**: Cleans and strips HTML tags using BeautifulSoup, and truncates overly long articles to safely fit within the LLM's context window.
- **Interactive Web Interface**: A sleek, tabbed UI that renders summaries as Markdown, featuring:
  - Read summaries sorted by reverse chronological order.
  - **Instant Search**: A fast, client-side JavaScript search bar to filter articles by keyword or title.
- **Flat-File Storage**: Uses lightweight `json` files (`data/articles.json` and `feeds.json`) instead of a heavy database, making it portable and easy to version control.

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
   pip install -r requirements.txt
   ```
   *(Optional: If you intend to use Google Gemini, also run `pip install google-generativeai` and set the `GOOGLE_API_KEY` environment variable).*

4. **Pull the Ollama Model**:
   Make sure the default model is downloaded to your local Ollama instance:
   ```bash
   ollama pull llama3.1:8b
   ```

## Usage

### Managing Feeds & Prompts
Subscriptions and their respective AI persona prompts are managed in the `feeds.json` file in the root directory. 
To add a new feed, simply add a new object to the array:
```json
{
    "url": "https://newpublication.substack.com/feed",
    "prompt": ""
}
```
*If you leave the `"prompt"` field empty, the AI will automatically generate one for you on the next run.*

### Publishing
Run the provided bash script to fetch new articles, generate the static HTML, and push it to the `gh-pages` branch safely:
```bash
bash publish.sh
```
*Once pushed, the included GitHub Action will automatically deploy your site to GitHub Pages.*

## How it Works

1. **Initialization**: `publish.sh` securely extracts your historical `articles.json` from your deployment branch to ensure it remembers previously summarized articles.
2. **Data Extraction**: `worker.py` loops through `feeds.json` and fetches the latest RSS XML.
3. **Summarization**:
   - Checks if the article URL already exists in `data/articles.json`.
   - Uses `BeautifulSoup` to extract raw text from the Substack HTML payload.
   - Truncates text to prevent context window overflow.
   - Invokes Ollama to generate a summary based on the feed's custom system prompt.
4. **Templating**: Processes the collected data through `template.html` using Jinja2 to output a fully functional static `index.html`.
5. **Deployment**: `publish.sh` uses an orphan branch strategy to forcefully push only the required payload files (`index.html` and `data/articles.json`) to the `gh-pages` branch, keeping your master git history clean.
6. **GitHub Pages Setup**: To serve the statically generated site, navigate to your repository's **Settings > Pages**. Under the **Build and deployment** section, select **Deploy from a branch** as the source. Choose the `gh-pages` branch and the `/ (root)` folder, then click save. Your site will automatically be published whenever `publish.sh` updates the branch.

## Troubleshooting

- **`Error invoking Ollama`**: Ensure the Ollama app is running in the background and that you have pulled the requested model.
- **Missing Modules**: Ensure your virtual environment is active and all packages listed in the Installation step are fully installed.
- **Git Branch Errors**: If `publish.sh` fails due to uncommitted local changes, ensure your working directory is clean before running the script.