# OpenFoodFacts MCP Server

A Model Context Protocol (MCP) server that provides food product information tools through the OpenFoodFacts API. This server enables AI agents to look up products by barcode, search for products, and retrieve nutritional information, Nutri-Score, ingredients, and allergen data.

## Features

### 🍽️ Four Powerful Food Product Tools

1. **get_product_by_barcode** - Get detailed product information by barcode including nutrition facts, Nutri-Score, ingredients, and allergens
2. **search_products** - Search for food products by name, brand, or category with pagination support
3. **get_product_nutrition** - Get comprehensive nutrition facts including per-100g and per-serving values, plus Nutri-Score
4. **get_product_ingredients** - Get detailed ingredients including allergens, additives, NOVA group, and vegan/vegetarian analysis

### 📊 Rich Product Data

- **Product Information**: Name, brand, categories, labels, quantity
- **Nutrition Facts**: Energy, macronutrients, vitamins, minerals
- **Nutri-Score**: Grade (A-E) and detailed score
- **Eco-Score**: Environmental impact rating
- **NOVA Group**: Food processing level (1-4)
- **Ingredients Analysis**: Allergens, traces, additives, vegan/vegetarian status
- **Images**: Product image URLs

## Architecture

This repository provides:
- `openfoodfacts_mcp_server.py` - Main MCP server with OpenFoodFacts API tools
- `adapter_http.py` - FastAPI adapter exposing HTTP+SSE endpoints for MCP clients (e.g., n8n)
- `app.py` - Simple entrypoint that calls `main()` in `openfoodfacts_mcp_server.py`
- `Procfile` - Deployment configuration for platforms like Railway

## Requirements

- Python 3.8+
- httpx (for async HTTP requests)
- FastAPI and uvicorn (for HTTP adapter)

## Setup

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
& .venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Run the server

#### Option A: Run the FastAPI adapter (recommended for HTTP+SSE clients)

```powershell
& .venv\Scripts\Activate.ps1
uvicorn adapter_http:api --host 0.0.0.0 --port 8000 --timeout-keep-alive 120
```

The adapter will be available at `http://127.0.0.1:8000`.

#### Option B: Run the standalone MCP server

```powershell
python app.py
```

## Environment Variables

- `MCP_BEARER_TOKEN` (optional) — If set, the FastAPI adapter will require a matching Bearer token for `/mcp` requests

## HTTP+SSE Endpoints

When running the FastAPI adapter:

- `GET /mcp` — Create a session (returns `{ "session": "<id>" }`)
- `GET /mcp` with header `mcp-session-id: <id>` and `Accept: text/event-stream` — Open SSE stream for that session
- `POST /mcp` — Send an MCP envelope (JSON). Include header `mcp-session-id: <id>` to route responses to that session
- `GET /sse` — Standard SSE endpoint used by many MCP clients
- `POST /messages` — Alias for `POST /mcp`
- `GET /healthz` — Health check endpoint
- `GET /mcp_status` — Status check (shows if MCP module is loaded)

## Usage Examples

### 1. Get Product by Barcode

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_product_by_barcode",
    "arguments": {
      "barcode": "3017620422003"
    }
  }
}
```

**Response:**
```json
{
  "found": true,
  "barcode": "3017620422003",
  "product": {
    "product_name": "Nutella",
    "brands": "Ferrero",
    "nutriscore_grade": "e",
    "nova_group": 4
  },
  "nutrition": {
    "energy_kcal": 539,
    "fat": 30.9,
    "sugars": 56.3,
    "proteins": 6.3
  },
  "ingredients": {
    "allergens": "en:milk, en:nuts",
    "additives_tags": ["en:e322"]
  }
}
```

### 2. Search Products

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "search_products",
    "arguments": {
      "query": "organic oat milk",
      "page": 1,
      "page_size": 5
    }
  }
}
```

### 3. Get Product Nutrition

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_product_nutrition",
    "arguments": {
      "barcode": "3017620422003"
    }
  }
}
```

**Response includes:**
- `nutriscore`: Grade and score
- `per_100g`: Complete nutrition values per 100g
- `per_serving`: Nutrition values per serving (if available)

### 4. Get Product Ingredients

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "get_product_ingredients",
    "arguments": {
      "barcode": "3017620422003"
    }
  }
}
```

**Response includes:**
- `ingredients_text`: Full ingredients list
- `allergens`: Allergen information
- `traces`: May contain traces
- `additives`: List of additives
- `nova_group`: Processing level
- `analysis`: Vegan/vegetarian/palm oil free status

## Integration with AI Agents

This MCP server is designed to work alongside:
- **PubChem MCP Server** - Get molecular information for food additives
- **USDA MCP Server** - Additional nutritional data
- **Recipe APIs** - For meal planning applications

### Example Workflow

1. User scans a product barcode with their phone
2. Agent calls `get_product_by_barcode` to retrieve product info
3. Agent checks Nutri-Score and allergens
4. Agent recommends healthier alternatives using `search_products`
5. Agent compares nutrition using `get_product_nutrition`

## Rate Limits

OpenFoodFacts API has the following rate limits:
- **100 req/min** for product queries
- **10 req/min** for search queries

This MCP server respects these limits. For bulk operations, consider using the OpenFoodFacts data dumps instead.

## Data Attribution

Data is provided by [Open Food Facts](https://world.openfoodfacts.org/) under the [Open Database License](https://opendatacommons.org/licenses/odbl/1.0/).

## Docker Deployment

A `Dockerfile` is included for containerized deployments:

```powershell
docker build -t openfoodfacts-mcp .
docker run -p 8000:8000 openfoodfacts-mcp
```

## Logging

The server logs to `rdkit_mcp.log` with rotation (1MB max, 5 backups). Logs include:
- Tool invocations
- RDKit availability status
- Analysis results
- Error messages

## Common SMILES Strings for Food Chemistry

- **Ethanol**: `CCO`
- **Vanillin**: `COC1=CC=C(C=C1)C=O`
- **Limonene**: `CC1=CCC(CC1)C(=C)C`
- **Menthol**: `CC(C)C1CCC(CC1)C(C)O`
- **Eugenol**: `C=CCC1=CC(=C(C=C1)O)OC`
- **Cinnamaldehyde**: `C=CC=CC(=O)`

Get SMILES from PubChem or your PubChem MCP server for any compound!

## License

This project uses RDKit which is licensed under the BSD 3-Clause License.

MIT License for this MCP server implementation.
