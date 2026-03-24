# Brewers Tailored Marketing Engine POC

A Streamlit-based proof-of-concept application for the Milwaukee Brewers that personalizes ticket promotions and marketing messaging based on fan segments, with optional AI-generated creative via Ollama.

## Features

- **Fan Segmentation**: Categorizes fans into Die-hard, F&B, Family, and Social segments
- **Tailored Marketing**: Generates segment-specific messaging, tone, and creative guidance
- **AI Creative Generation**: Uses Ollama (local LLM) to generate marketing copy alongside rule-based output
- **Dynamic Pricing**: Integrates game schedule and promotional pricing data
- **CRM Export**: Builds CRM-ready export previews per segment
- **Interactive UI**: Built with Streamlit for easy exploration and testing

## Project Structure

```
brewers_app/
├── brewers_poc_app.py                 # Main Streamlit application
├── generate_creative.py              # Batch creative generation script
├── ollama_service.py                  # Ollama API client
├── config.yml                         # App and Ollama configuration
├── requirements_brewers_poc.txt       # Python dependencies
├── data/
│   ├── GameTicketPromotionPrice.csv   # Game schedule and pricing data
│   └── brewers mock fan data.csv     # Sample fan data
├── results/                           # Generated creative JSON files
└── README.md
```

## Setup

### Prerequisites

- **Python 3.10+**
- **Ollama** (for AI creative generation): Download from [ollama.com](https://ollama.com)

### 1. Create a Virtual Environment

```powershell
python -m venv venv
```

### 2. Set PowerShell Execution Policy (Windows only, one-time)

If you get a script execution error when activating the venv:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Activate the Virtual Environment

```powershell
.\venv\Scripts\Activate.ps1
```

Your terminal prompt should now start with `(venv)`.

### 4. Install Dependencies

```powershell
pip install -r requirements_brewers_poc.txt
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

Make sure your venv is activated and Ollama is running, then:

```powershell
.\venv\Scripts\streamlit.exe run brewers_poc_app.py
```

The app will open in your browser at `http://localhost:8501`.

### Using the App

1. Select a **target segment** and **game** from the sidebar
2. Click **"Generate AI Creative"** to produce LLM-generated marketing copy
3. View rule-based and AI-generated creative side by side
4. Preview and export CRM-ready data

## Configuration

Edit `config.yml` to change:

- **Ollama settings**: base URL, model, timeout
- **App settings**: page title, layout, data file paths

## Troubleshooting

- **`ModuleNotFoundError`**: Make sure your venv is activated and dependencies are installed
- **"Ollama service is not running"**: Run `ollama serve` in a separate terminal
- **"Generation completed but LLM creative was not produced"**: Check Ollama is running and the model is pulled
- **PowerShell script execution blocked**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

## Notes

- This is a proof-of-concept application
- Sample CSV data is required in the project root directory
- Segment definitions and messaging guidance are configured in the app and generation script
