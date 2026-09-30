# openfoodfacts-mcp

An [MCP](https://modelcontextprotocol.io) server for [Open Food Facts](https://world.openfoodfacts.org/),
the open database of about 4 million packaged food products. An assistant can scan-and-ask
("is this barcode vegan?"), compare Nutri-Scores, or find organic cereals with an A grade.

## Tools

| Tool | What it does |
| --- | --- |
| `get_product_by_barcode` | Summary, nutrition and ingredients for one product. |
| `get_product_nutrition` | Per-100 g and per-serving nutrients, plus the Nutri-Score. |
| `get_product_ingredients` | Ingredients, allergens, traces, additives, NOVA group, and vegan/vegetarian/palm-oil flags. |
| `get_products_by_barcodes` | Up to 100 products at once, reporting any barcodes not found. |
| `search_products` | Full-text search. |
| `advanced_search` | Filter by category, brand, label, Nutri-Score, NOVA group, allergen, country and more. |
| `get_taxonomy_suggestions` | Autocomplete tag values, e.g. categories starting with "choco". |
| `list_facets` | All values of a facet (labels, brands, ...) with product counts. |
| `get_products_by_facets` | Products matching one or more facet values. |
| `get_facet_knowledge_panel` | The explanatory panel Open Food Facts shows for a facet value. |

## Quick start

```bash
cd openfoodfacts-mcp
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                   # offline, with the API mocked
LIVE_TESTS=1 pytest      # also runs smoke tests against the real API
```

No API key is needed.

### Claude Desktop (stdio)

```json
{
  "mcpServers": {
    "openfoodfacts": { "command": "/path/to/openfoodfacts-mcp/.venv/bin/openfoodfacts-mcp" }
  }
}
```

### Remote server (Streamable HTTP)

```bash
MCP_TRANSPORT=http MCP_BEARER_TOKEN=$(openssl rand -hex 32) openfoodfacts-mcp   # http://0.0.0.0:8000/mcp

docker build -t openfoodfacts-mcp .
docker run -p 8000:8000 -e MCP_BEARER_TOKEN openfoodfacts-mcp
```

Clients send `Authorization: Bearer <token>`. `GET /healthz` is unauthenticated.
The environment variables are the same as for [usda-food-mcp](../usda-food-mcp#run-as-a-remote-server-streamable-http),
minus the API key.

## Design notes

- **The server enforces Open Food Facts' published rate limits:** 100 product lookups,
  10 searches and 2 facet queries per minute. A request over the limit fails right away
  with a "retry in N seconds" message, so the assistant doesn't hang and the API doesn't
  get hammered.
- **User input can't change the request path.** Barcodes must be digits, and facet values
  must be tag-shaped (`en:organic`, `breakfast-cereals`). Anything like `../` is rejected
  before a request is made.
- **Responses are trimmed.** Product lookups request only the fields each tool uses,
  instead of multi-hundred-KB product records.
- **The client identifies itself** with a User-Agent pointing at this repo, as Open Food
  Facts asks.
- **Tests run offline** against a mocked API. A small live smoke suite can be run by hand
  (`LIVE_TESTS=1 pytest`, or "Run workflow" on the Actions tab).

## History

I built this in January 2026, starting from the same template as my other servers. In
September 2026 I rewrote it on MCP SDK v2 and added:
- the input validation and rate limiting
- offline tests (the original tests all called the live API)
- the security fixes shared with the other servers

I also merged the single-facet and multi-facet tools into one.

## Data and license

Data © Open Food Facts contributors, under the [Open Database License](https://opendatacommons.org/licenses/odbl/1.0/).
Code is MIT, see [LICENSE](LICENSE).
