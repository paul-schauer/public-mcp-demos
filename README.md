# public-mcp-demos

[![usda-food-mcp](https://github.com/paul-schauer/public-mcp-demos/actions/workflows/usda-food-mcp.yml/badge.svg)](https://github.com/paul-schauer/public-mcp-demos/actions/workflows/usda-food-mcp.yml)
[![rdkit-mcp](https://github.com/paul-schauer/public-mcp-demos/actions/workflows/rdkit-mcp.yml/badge.svg)](https://github.com/paul-schauer/public-mcp-demos/actions/workflows/rdkit-mcp.yml)
[![openfoodfacts-mcp](https://github.com/paul-schauer/public-mcp-demos/actions/workflows/openfoodfacts-mcp.yml/badge.svg)](https://github.com/paul-schauer/public-mcp-demos/actions/workflows/openfoodfacts-mcp.yml)

[Model Context Protocol](https://modelcontextprotocol.io) servers I built in 2025 and early 2026 to give
AI agents access to food and chemistry data, then came back to and rewrote in September 2026. Together
they let an assistant go from a product barcode, to its nutrition, to the chemistry of
its flavor compounds.

| Project | Data source | Built | Tools |
| --- | --- | --- | --- |
| [usda-food-mcp](usda-food-mcp/) | USDA FoodData Central nutrition database | Aug 2025 | 4 |
| [rdkit-mcp](rdkit-mcp/) | RDKit cheminformatics, run locally | Nov 2025 | 5 |
| [openfoodfacts-mcp](openfoodfacts-mcp/) | Open Food Facts packaged-product database | Jan 2026 | 10 |

All three share the same structure:
- Python 3.11+ on the official MCP SDK v2
- stdio for desktop clients, and stateless Streamable HTTP with bearer auth for remote ones
- tests that run offline, a non-root Docker image, and CI for each project

## Repository history

Each project was developed in its own repo and imported here with its full commit history,
so `git log -- <project>` shows how it actually evolved. Commits up to each import are
the original work. Commits after it are the 2026 rewrite.
