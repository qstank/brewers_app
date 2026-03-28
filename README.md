# Brewers Tailored Marketing Engine POC

> **Disclaimer:**
> Image generation with Ollama's image models (e.g., `x/z-image-turbo`) requires a large amount of RAM (typically 16GB or more, depending on the model). Insufficient memory will result in errors or failed image generation. For best results, close other applications and ensure your system meets the model's requirements. See the Ollama documentation for details.

## Image Generation Feature

The app supports **AI-powered image generation** for marketing creative using Ollama's local image models (e.g., `x/z-image-turbo`).

- **How it works:**
   - For each creative (rule-based or LLM), an "image concept" prompt is generated based on segment rules and game context.
   - Click the **🖼️ Generate Image** button in the UI to create an image from the current creative's concept prompt.
   - Images are generated via the Ollama API and displayed directly in the app.

- **Requirements:**
   - Ollama must be running locally (`ollama serve`)
   - The `x/z-image-turbo` (or compatible) image model must be pulled: `ollama pull x/z-image-turbo`
   - Sufficient RAM (image models require significant memory; see Ollama docs)

- **Troubleshooting:**
   - If you see "Not enough RAM for image model", close other applications or use a machine with more memory.
   - If you see "Model is not available", ensure the image model is pulled and listed in Ollama (`ollama list`).
   - Check Ollama logs for additional errors.

You can change the image model in `config.yml` under `ollama.image_model` if needed.

A Streamlit-based proof-of-concept application for the Milwaukee Brewers that personalizes ticket promotions and marketing messaging by fan segment, with optional AI-generated creative via a local Ollama model.

## Features

- **Fan Segmentation**: Categorizes fans into Die-hard, F&B, Family, and Social segments
- **Tailored Marketing**: Generates segment-specific messaging, tone, and creative guidance
- **AI Creative Generation**: Uses Ollama (local LLM) to generate marketing copy alongside rule-based output
- **Fan-Level Targeting**: Optional fan picker to generate creative personalized to an individual fan's profile
- **Campaign Notes**: Optional free-text campaign notes injected into the LLM prompt for thematic guidance
- **Dynamic Game Context**: Automatically injects day/night, day-of-week, rivalry, and broadcast context into prompts
- **CRM Export**: Builds CRM-ready export previews per segment with download support
- **Interactive UI**: Built with Streamlit for easy exploration and testing

## Project Structure

```
brewers_app/
├── brewers_poc_app.py                 # Streamlit UI layer
├── creative_engine.py                 # Shared business logic (segments, creative, data)
├── generate_creative.py               # CLI batch generation wrapper
├── ollama_service.py                  # Ollama API client
├── config.yml                         # App and Ollama configuration
├── requirements.txt                  # Python dependencies
├── prompts/
│   ├── creative_email.txt             # LLM prompt template with placeholders
│   ├── segment_guidance.yml           # Segment tone, hooks, image, CTA definitions
│   ├── rules_die-hard.txt             # Die-hard segment style rules
│   ├── rules_fb.txt                   # F&B segment style rules
│   ├── rules_family.txt               # Family segment style rules
│   └── rules_social.txt               # Social segment style rules
├── data/
│   ├── GameTicketPromotionPrice.csv   # Game schedule and pricing data
│   └── brewers mock fan data.csv      # Sample fan data
├── results/                           # Generated creative JSON files
└── README.md
```

## Setup

### Prerequisites

- **Python 3.10+**
- **Ollama** (for AI creative generation): Download from [ollama.com](https://ollama.com)

### macOS Quick Start


```bash
brew install python@3.14
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ollama pull mistral
streamlit run brewers_poc_app.py
```

If Ollama is not already running in the background, start it with:

```bash
ollama serve
```

### Windows Setup

### 1. Create a Virtual Environment

```powershell
python -m venv .venv
```

### 2. Set PowerShell Execution Policy (Windows only, one-time)

If you get a script execution error when activating the venv:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Activate the Virtual Environment

```powershell
.\.venv\Scripts\Activate.ps1
```

Your terminal prompt should now start with `(.venv)`.

### 4. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 5. Set Up Ollama (for AI Creative Generation)

1. Install Ollama from [ollama.com](https://ollama.com)
2. Pull the mistral model:
   ```powershell
   ollama pull mistral
   ```
3. Start the Ollama service:
   ```powershell
   ollama serve
   ```

You can change the model in `config.yml` under `ollama.model`.

## Running the Application

Make sure your .venv is activated. Ollama is only required if you want AI-generated creative.

macOS:

```bash
source .venv/bin/activate
streamlit run brewers_poc_app.py
```

Windows PowerShell:

```powershell
.\.venv\Scripts\streamlit.exe run brewers_poc_app.py
```

The app will open in your browser at `http://localhost:8501`.

### Using the App

1. Select a **target segment** and **game** from the sidebar
2. Optionally add a **campaign note** (e.g. "rivalry angle", "giveaway night") — this is injected into the LLM prompt only
3. Optionally select a **specific fan** to personalize the creative to their profile
4. Click **"Generate AI Creative"** to produce LLM-generated marketing copy
5. View rule-based and AI-generated creative side by side
6. Preview and export CRM-ready data

## Architecture Notes

- **`creative_engine.py`** is the single source of truth for segment definitions, data loading, rule-based creative, and LLM creative generation. Both the Streamlit app and the CLI script import from it.
- **`brewers_poc_app.py`** is a thin UI layer — it renders creative and handles Streamlit state, but contains no business logic.
- **`prompts/`** contains all externalized prompt content: the main LLM prompt template (`creative_email.txt`), segment guidance (`segment_guidance.yml`), and per-segment style rules (`rules_*.txt`). Changes to prompts require no code changes.
- **`generate_creative.py`** is a thin CLI wrapper for batch generation with `--segment`, `--game`, `--use-llm`, `--limit`, and `--workers` options.
- **`ollama_service.py`** handles Ollama API communication (health checks, model listing, text/JSON generation). Uses Ollama's native `format: "json"` parameter for reliable structured output.
- Ollama is optional for basic app usage, but required for the AI-generated side-by-side comparison.

## Configuration

Edit `config.yml` to change:

- **Ollama settings**: base URL, model, timeout
- **App settings**: page title, layout, data file paths

## Troubleshooting

- **`ModuleNotFoundError`**: Make sure your venv is activated and dependencies are installed
- **"Ollama is not running"**: Run `ollama serve` in a separate terminal, unless Ollama is already running in the background
- **"Model is not available"**: Pull the configured model with `ollama pull mistral`
- **"Model returned a response, but it could not be converted"**: The LLM responded, but not in the expected JSON structure; try regenerating or switch to a model that follows structured output more reliably
- **PowerShell script execution blocked**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

## Notes

- This is a proof-of-concept application
- Sample CSV data is required in the `data/` directory
- Segment definitions and messaging guidance live in `prompts/segment_guidance.yml` and `prompts/rules_*.txt`
- Dates in generated creative use "day-of-week, DD Month" format (e.g. "Tuesday, 17 March")
