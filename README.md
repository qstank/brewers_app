# Brewers Tailored Marketing Engine POC

A Streamlit-based proof-of-concept application for the Milwaukee Brewers that personalizes ticket promotions and marketing messaging based on fan segments.

## Features

- **Fan Segmentation**: Categorizes fans into Die-hard, F&B, Family, and Social segments
- **Tailored Marketing**: Generates segment-specific messaging, tone, and creative guidance
- **Dynamic Pricing**: Integrates game schedule and promotional pricing data
- **Interactive UI**: Built with Streamlit for easy exploration and testing

## Project Structure

```
brewers_app/
├── brewers_poc_app.py                      # Main Streamlit application
├── requirements_brewers_poc.txt            # Python dependencies
├── GameTicketPromotionPrice.csv            # Game schedule and pricing data
├── brewers mock fan data.csv               # Sample fan data (required at runtime)
├── README.md                               # This file
└── .gitignore                              # Git ignore rules
```

## Setup

### Prerequisites

- Python 3.8+
- pip or conda package manager

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd brewers_app
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements_brewers_poc.txt
   ```

3. Ensure required data files are in place:
   - `GameTicketPromotionPrice.csv`
   - `brewers mock fan data.csv`

## Running the Application

```bash
streamlit run brewers_poc_app.py
```

The application will open in your default browser at `http://localhost:8501`.

## Development

### Dependencies

- **streamlit**: Web app framework
- **pandas**: Data manipulation and analysis

### Adding Dependencies

When adding new packages:
1. Install the package: `pip install <package-name>`
2. Update requirements: `pip freeze > requirements_brewers_poc.txt`

## Notes

- This is a proof-of-concept application
- Sample CSV data is required in the project root directory
- Segment definitions and messaging guidance are hardcoded in the app

## License

[Add license information if applicable]
