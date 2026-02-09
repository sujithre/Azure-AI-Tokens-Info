# Azure OpenAI Token Analysis

A Python script that discovers all Azure OpenAI and AI Services resources across your subscriptions and extracts monthly token usage (input + output) per deployment and model, exporting the results to CSV.

## Prerequisites

- **Python 3.8+**
- **Azure CLI** installed and authenticated (`az login`)
- An Azure account with access to one or more Azure OpenAI / AI Services resources
- The following Python packages (see `requirements.txt`):
  - `pandas`
  - `azure-identity`
  - `azure-mgmt-resourcegraph`

## Setup

1. **Clone the repository**

   ```bash
   git clone <repo-url>
   cd Azure-AI-Tokens-Info
   ```

2. **Create a virtual environment**

   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**

   - **Windows (PowerShell)**
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **Windows (CMD)**
     ```cmd
     .venv\Scripts\activate.bat
     ```
   - **Linux / macOS**
     ```bash
     source .venv/bin/activate
     ```

4. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

5. **Authenticate with Azure**

   ```bash
   az login
   ```

## Usage

**Default — previous calendar month (no arguments needed):**

```bash
python tokensv2.py
```

**Specific month:**

```bash
python tokensv2.py --start-date 2026-01-01 --end-date 2026-01-31
```

**Custom date range:**

```bash
python tokensv2.py --start-date 2025-10-01 --end-date 2025-12-31
```

**Show help:**

```bash
python tokensv2.py --help
```

| Parameter | Format | Default |
|-----------|--------|---------|
| `--start-date` | `YYYY-MM-DD` | First day of previous month |
| `--end-date` | `YYYY-MM-DD` | Last day of previous month |

The script will:

1. Verify Azure CLI authentication.
2. Discover all Azure OpenAI and AI Services resources using Azure Resource Graph.
3. Query `ProcessedPromptTokens` (input) and `GeneratedTokens` (output) metrics for each resource.
4. Map deployment names to model names via the Azure Cognitive Services deployment API.
5. Export a CSV file in the working directory.

## Sample Output

### Console

```
Azure OpenAI Token Analysis - COMPLETE VERSION
============================================================
✅ Authenticated as: user@example.com
✅ Current subscription: My-Subscription
📅 Analysis Period: January 01, 2026 to January 31, 2026
✅ Azure SDK authentication successful
🔍 Discovering Azure OpenAI and AIServices resources with subscription info...
✅ Found 2 Azure OpenAI/AIServices resource(s)

🔍 Processing: AI (AIServices) (Subscription: XXXX)
  ✅ Found 1 model(s) with token usage (input + output combined)

📊 Token Usage Summary (January 2026)
========================================================
📈 Overall Summary:
🎯 Total Tokens: 433,927
🏢 OpenAI Resources: 2
🤖 Unique Models: 3
✅ Analysis complete!
```

### CSV (`azure_openai_tokens_January_2026_<timestamp>.csv`)

| ID | DeploymentName | ModelName | Processed Inference Tokens (Sum) | Month | Subscription Id | Subscription Name | Kind |
|----|---------------|-----------|----------------------------------|-------|-----------------|-------------------|------|
| /subscriptions/.../AI | gpt-4.1 | gpt-4.1 | 11579 | January 2026 | XXXX-... | XXXX | AIServices |
| /subscriptions/.../admin--eastus2 | computer-use-preview | computer-use-preview | 274257 | January 2026 | XXXX-... | XXXX | AIServices |
| /subscriptions/.../admin--eastus2 | gpt-4.1 | gpt-4.1 | 148091 | January 2026 | XXXX-... | XXXX | AIServices |

## Project Structure

```
Azure-AI-Tokens-Info/
├── tokensv2.py          # Main analysis script
├── requirements.txt     # Python dependencies
├── README.md            # This file
└── .gitignore
```

## License

Internal use only.
