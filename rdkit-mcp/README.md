# RDKit MCP Server

A Model Context Protocol (MCP) server that provides molecular chemistry tools through RDKit for food chemistry applications. This server enables AI agents to analyze molecular properties, find similar molecules, generate 3D structures, and check safety properties - perfect for culinary innovation and food chemistry applications.

## Features

### 🧪 Four Powerful Chemistry Tools

1. **analyze_molecular_properties** - Analyze molecular properties including LogP, molecular weight, and solubility predictions for culinary applications
2. **find_similar_molecules** - Find structurally similar molecules using Tanimoto similarity (ideal for finding flavor substitutes)
3. **generate_3d_structure** - Generate 3D molecular structures and 2D visualization images
4. **check_safety_properties** - Check safety and drug-likeness properties using QED for preliminary safety insights

### 🍽️ Built for Food Chemistry

- **Solubility Predictions**: Understand whether compounds are water-soluble (for syrups/brines), alcohol-soluble (for tinctures), or fat-soluble (for oil infusions)
- **Flavor Substitute Finder**: Find structurally similar compounds when ingredients are expensive or unavailable
- **3D Visualization**: Generate molecular visualizations for packaging, labels, or educational materials
- **Safety Insights**: Preliminary safety checks using QED properties before consulting FDA GRAS databases

## Architecture

This repository provides:
- `rdkit_mcp_server.py` - Main MCP server with RDKit chemistry tools
- `adapter_http.py` - FastAPI adapter exposing HTTP+SSE endpoints for MCP clients (e.g., n8n)
- `app.py` - Simple entrypoint that calls `main()` in `rdkit_mcp_server.py`
- `Procfile` - Deployment configuration for platforms like Railway

## Requirements

- Python 3.8+
- RDKit (automatically installs with requirements)
- Pillow (for image generation)

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
- `GET /mcp_status` — Status check (shows if RDKit is available)

## Usage Examples

### 1. Analyze Molecular Properties (Solubility Prediction)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "analyze_molecular_properties",
    "arguments": {
      "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O"
    }
  }
}
```

**Response:**
```json
{
  "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
  "logP": 1.19,
  "molecular_weight": 180.16,
  "solubility_prediction": "Alcohol-soluble (amphiphilic). Best for: tinctures, high-proof extractions",
  "molecular_formula": "C9H8O4"
}
```

### 2. Find Similar Molecules (Flavor Substitutes)

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "find_similar_molecules",
    "arguments": {
      "target_smiles": "CC1=CC=C(C=C1)C=O",
      "candidate_smiles_list": [
        "COC1=CC=C(C=C1)C=O",
        "CC1=CC=CC=C1C=O",
        "O=CC1=CC=CC=C1"
      ],
      "threshold": 0.7
    }
  }
}
```

### 3. Generate 3D Structure

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "generate_3d_structure",
    "arguments": {
      "smiles": "CCO",
      "include_image": true
    }
  }
}
```

**Response includes:**
- `mol_block`: 3D coordinates in MOL format
- `image_base64`: Base64-encoded PNG image of the 2D structure
- `molecular_formula`: Chemical formula

### 4. Check Safety Properties

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "check_safety_properties",
    "arguments": {
      "smiles": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"
    }
  }
}
```

**Response includes:**
- `qed_score`: Drug-likeness score
- `safety_notes`: Preliminary safety insights
- `properties`: Detailed molecular properties
- `recommendation`: Reminder to verify with FDA GRAS databases

## Integration with AI Agents

This MCP server is designed to work alongside:
- **PubChem MCP Server** - Get SMILES strings for compounds
- **USDA MCP Server** - Nutritional data for food applications
- **OpenFDA API** - Safety and regulatory information

### Example Workflow

1. Agent asks: "Can I extract vanilla flavor with alcohol?"
2. Query PubChem for Vanillin SMILES: `COC1=CC=C(C=C1)C=O`
3. Use `analyze_molecular_properties` to check LogP
4. Response shows LogP ≈ 1.2 → "Alcohol-soluble"
5. Agent recommends high-proof alcohol extraction

## Docker Deployment

A `Dockerfile` is included for containerized deployments:

```powershell
docker build -t rdkit-mcp .
docker run -p 8000:8000 rdkit-mcp
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
