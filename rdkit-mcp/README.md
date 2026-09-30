# rdkit-mcp

An [MCP](https://modelcontextprotocol.io) server that gives AI assistants cheminformatics
tools from [RDKit](https://www.rdkit.org/), framed for food and flavor chemistry. It
answers questions like "will vanilla extract better in vodka or oil?" and "what
compounds are structurally close to vanillin?"

## Tools

| Tool | What it does |
| --- | --- |
| `analyze_molecular_properties` | LogP, molecular weight, H-bond donors/acceptors, TPSA and rotatable bonds, plus a rough water/alcohol/fat extraction guide. |
| `find_similar_molecules` | Ranks candidates by Tanimoto similarity of Morgan fingerprints, e.g. to find flavor substitutes. |
| `generate_3d_structure` | ETKDGv3 conformer with MMFF94 (or UFF) optimization, returned as a MOL block. |
| `draw_molecule` | 2D structure diagram, returned as an MCP image. |
| `check_safety_properties` | QED drug-likeness, size and lipophilicity checks, and structural alerts. A prompt for further research, not a safety verdict. |

All tools take SMILES strings. Pair this server with a PubChem lookup when you only have
compound names.

### Example

> **You:** Can I extract vanilla flavor with alcohol?
>
> The assistant looks up vanillin (`COc1cc(C=O)ccc1O`) and calls
> `analyze_molecular_properties`. It gets LogP ≈ 1.2, which falls in the "alcohol-soluble"
> band, so it recommends a high-proof extraction.

Some useful SMILES:

| Compound | SMILES |
| --- | --- |
| Vanillin | `COc1cc(C=O)ccc1O` |
| Ethyl vanillin | `CCOc1cc(C=O)ccc1O` |
| Limonene | `CC1=CCC(CC1)C(=C)C` |
| Menthol | `CC(C)C1CCC(C)CC1O` |
| Eugenol | `C=CCc1ccc(O)c(OC)c1` |
| Cinnamaldehyde | `O=C/C=C/c1ccccc1` |

## Quick start

```bash
cd rdkit-mcp
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

No API key is needed, since everything runs locally.

### Claude Desktop (stdio)

```json
{
  "mcpServers": {
    "rdkit": { "command": "/path/to/rdkit-mcp/.venv/bin/rdkit-mcp" }
  }
}
```

### Remote server (Streamable HTTP)

```bash
MCP_TRANSPORT=http MCP_BEARER_TOKEN=$(openssl rand -hex 32) rdkit-mcp   # http://0.0.0.0:8000/mcp

docker build -t rdkit-mcp .
docker run -p 8000:8000 -e MCP_BEARER_TOKEN rdkit-mcp
```

Clients send `Authorization: Bearer <token>`. `GET /healthz` is unauthenticated.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MCP_TRANSPORT` | `stdio` (`http` in Docker) | `stdio` or `http` |
| `MCP_BEARER_TOKEN` | required for `http` | Shared secret that clients send as a bearer token |
| `PORT` | `8000` | HTTP port |
| `ALLOW_UNAUTHENTICATED` | unset | Set to `1` to serve HTTP without a token (local testing only) |

## Design notes

- **The chemistry is separate from the protocol.** `chemistry.py` is plain RDKit code with
  no MCP imports, tested on its own. `server.py` only declares tools.
- **CPU-heavy work stays off the event loop.** Tools are synchronous functions, so the MCP
  SDK runs them in a worker thread instead of blocking other requests.
- **Inputs are bounded.** SMILES length, candidate list size, image size and molecule
  size for 3D embedding are all capped, and conformer embedding has a timeout, so one
  request can't monopolize the server.
- **RDKit logging is silenced**, because its parse warnings go to stderr and would corrupt
  the stdio transport.

## History

I built the first version in November 2025 by adapting my
[USDA server](../usda-food-mcp), which is why it started with the same hand-written
HTTP adapter. In September 2026 I rewrote it on MCP SDK v2. The rewrite:
- fixed several SMILES strings in the docs that didn't match their compound names
- replaced the deprecated Morgan fingerprint API
- split image rendering into its own tool that returns real MCP image content
- added the input limits and the security fixes shared with the other servers

## License

MIT, see [LICENSE](LICENSE). RDKit is BSD-3-Clause.
