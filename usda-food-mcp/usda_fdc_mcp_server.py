#!/usr/bin/env python3
import sys
import sys
try:
    """
    USDA Food Data Central (FDC) MCP Server

    This server provides access to the USDA Food Data Central API through MCP tools.
    It allows searching for foods, getting detailed food information, and listing foods.
    """

    import asyncio
    import json
    import logging
    import logging.handlers
    from dotenv import load_dotenv
    import os
    from typing import Any, Dict, List, Optional, Union

    import httpx
    from mcp.server.fastmcp import FastMCP

    # Load environment variables from .env file
    load_dotenv()

    # Set up logging to file only (not stdout to avoid interfering with MCP)
    logger = logging.getLogger("usda-fdc-mcp")
    logger.setLevel(logging.INFO)

    # Configure logging to write to file only
    file_handler = logging.handlers.RotatingFileHandler(
        'usda_fdc_mcp.log',
        maxBytes=1024*1024,  # 1MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

    # Prevent logging to stdout/stderr
    logger.propagate = False

    # API Configuration
    BASE_URL = "https://api.nal.usda.gov/fdc"
    API_VERSION = "v1"

    # Initialize the MCP server
    app = FastMCP("usda-fdc")

    # Initialize the FDC client at module level
    api_key = os.getenv("USDA_FDC_API_KEY")
except Exception as e:
    import traceback
    print("[SERVER TOP-LEVEL ERROR]", file=sys.stderr)
    print(str(e), file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    # Do not exit on import errors; allow the adapter to report a meaningful error
    logger = logging.getLogger("usda-fdc-mcp") if 'logging' in globals() else None
    if logger:
        try:
            logger.error(f"Top-level import error: {e}")
        except Exception:
            pass
    # Safe fallback values so module remains importable
    BASE_URL = "https://api.nal.usda.gov/fdc"
    API_VERSION = "v1"
    class Dummy:
        pass
    app = Dummy()
    api_key = None

# If API key is missing, do not exit; log and proceed (tools will error when called)
if not api_key:
    try:
        logger.error("USDA_FDC_API_KEY environment variable not set")
        logger.info("Please get your free API key from: https://fdc.nal.usda.gov/api-key-signup.html")
    except Exception:
        pass

class FDCAPIClient:
    """Client for interacting with the USDA Food Data Central API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = f"{BASE_URL}/{API_VERSION}"
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict] = None, 
        json_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request to the FDC API."""
        url = f"{self.base_url}/{endpoint}"
        
        # Add API key to params
        if params is None:
            params = {}
        params["api_key"] = self.api_key
        
        try:
            if method.upper() == "GET":
                response = await self.client.get(url, params=params)
            elif method.upper() == "POST":
                response = await self.client.post(url, params=params, json=json_data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise Exception(f"API request failed: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            raise Exception(f"Request failed: {str(e)}")
    
    async def get_food(
        self, 
        fdc_id: str, 
        format_type: str = "full", 
        nutrients: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Get details for a single food item by FDC ID."""
        params = {"format": format_type}
        if nutrients:
            params["nutrients"] = ",".join(map(str, nutrients))
        
        return await self._make_request("GET", f"food/{fdc_id}", params=params)
    
    async def get_foods(
        self, 
        fdc_ids: List[str], 
        format_type: str = "full", 
        nutrients: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """Get details for multiple food items by FDC IDs."""
        if len(fdc_ids) > 20:
            raise ValueError("Maximum of 20 FDC IDs allowed")
        
        data = {
            "fdcIds": [int(fdc_id) for fdc_id in fdc_ids],
            "format": format_type
        }
        if nutrients:
            data["nutrients"] = nutrients
        
        return await self._make_request("POST", "foods", json_data=data)
    
    async def search_foods(
        self,
        query: str,
        data_type: Optional[List[str]] = None,
        page_size: int = 50,
        page_number: int = 1,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        brand_owner: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for foods using keywords."""
        data = {
            "query": query,
            "pageSize": min(page_size, 200),  # API max is 200
            "pageNumber": page_number
        }
        
        if data_type:
            data["dataType"] = data_type
        if sort_by:
            data["sortBy"] = sort_by
        if sort_order:
            data["sortOrder"] = sort_order
        if brand_owner:
            data["brandOwner"] = brand_owner
        
        return await self._make_request("POST", "foods/search", json_data=data)
    
    async def list_foods(
        self,
        data_type: Optional[List[str]] = None,
        page_size: int = 50,
        page_number: int = 1,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get a paged list of foods."""
        data = {
            "pageSize": min(page_size, 200),  # API max is 200
            "pageNumber": page_number
        }
        
        if data_type:
            data["dataType"] = data_type
        if sort_by:
            data["sortBy"] = sort_by
        if sort_order:
            data["sortOrder"] = sort_order
        
        return await self._make_request("POST", "foods/list", json_data=data)


# Global FDC client instance and event loop
fdc_client: Optional[FDCAPIClient] = None
loop: Optional[asyncio.AbstractEventLoop] = None

# If an API key is available at import time, initialize the FDC client so
# callers that import this module (for example the HTTP adapter) can use the
# tool functions without running the full `main()` process.
try:
    if api_key and fdc_client is None:
        fdc_client = FDCAPIClient(api_key)
        logger.info("Initialized module-level FDCAPIClient at import time")
except Exception as e:
    # Non-fatal: leave fdc_client as None and let callers handle errors.
    logger.warning(f"Could not initialize FDCAPIClient at import: {e}")

async def cleanup():
    """Clean up resources."""
    global fdc_client
    if fdc_client:
        logger.info("Closing FDC client...")
        await fdc_client.client.aclose()
        fdc_client = None





@app.tool()
async def get_food(fdc_id: str, format_type: str = "full", nutrients: Optional[List[int]] = None) -> Dict[str, Any]:
    """Get details for a single food item by FDC ID."""
    print(f"[SERVER DEBUG] get_food called with fdc_id={fdc_id}, format_type={format_type}, nutrients={nutrients}", file=sys.stderr)
    global fdc_client
    if fdc_client is None:
        raise Exception("FDC API client not initialized.")
    return await fdc_client.get_food(fdc_id, format_type, nutrients)

@app.tool()
async def get_foods(fdc_ids: List[str], format_type: str = "full", nutrients: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    """Get details for multiple food items by FDC IDs."""
    print(f"[SERVER DEBUG] get_foods called with fdc_ids={fdc_ids}, format_type={format_type}, nutrients={nutrients}", file=sys.stderr)
    global fdc_client
    if fdc_client is None:
        raise Exception("FDC API client not initialized.")
    return await fdc_client.get_foods(fdc_ids, format_type, nutrients)

@app.tool()
async def search_foods(query: str, data_type: Optional[List[str]] = None, page_size: int = 50, page_number: int = 1, sort_by: Optional[str] = None, sort_order: Optional[str] = None, brand_owner: Optional[str] = None) -> Dict[str, Any]:
    """Search for foods using keywords."""
    print(f"[SERVER DEBUG] search_foods called with query={query}, data_type={data_type}, page_size={page_size}, page_number={page_number}, sort_by={sort_by}, sort_order={sort_order}, brand_owner={brand_owner}", file=sys.stderr)
    global fdc_client
    if fdc_client is None:
        raise Exception("FDC API client not initialized.")
    return await fdc_client.search_foods(query, data_type, page_size, page_number, sort_by, sort_order, brand_owner)

@app.tool()
async def list_foods(data_type: Optional[List[str]] = None, page_size: int = 50, page_number: int = 1, sort_by: Optional[str] = None, sort_order: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get a paged list of foods."""
    print(f"[SERVER DEBUG] list_foods called with data_type={data_type}, page_size={page_size}, page_number={page_number}, sort_by={sort_by}, sort_order={sort_order}", file=sys.stderr)
    global fdc_client
    if fdc_client is None:
        raise Exception("FDC API client not initialized.")
    return await fdc_client.list_foods(data_type, page_size, page_number, sort_by, sort_order)




def main():
    """Main entry point for the MCP server."""
    global fdc_client
    try:
        # Initialize the FDC client
        fdc_client = FDCAPIClient(api_key)
        # Run the server
        logger.info("Starting USDA Food Data Central MCP Server...")
        logger.info("Available tools: get_food, get_foods, search_foods, list_foods")
        # Use explicit transport compatible with FastMCP.run signature
        # FastMCP.run(transport: 'stdio'|'sse'|'streamable-http', mount_path: Optional[str] = None)
        app.run('streamable-http')
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        print(f"[SERVER DEBUG] Server error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise
    finally:
        # Clean up resources
        if fdc_client and fdc_client.client:
            asyncio.run(fdc_client.client.aclose())


async def handle_http_envelope(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Handle an incoming MCP JSON-RPC envelope.

    Supports standard MCP protocol messages: initialize, tools/list, tools/call.
    """
    # Validate JSON-RPC 2.0 format
    if envelope.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": envelope.get("id"), "error": {"code": -32600, "message": "Invalid Request"}}

    method = envelope.get("method")
    req_id = envelope.get("id")
    params = envelope.get("params") or {}

    if method == "initialize":
        # Return server capabilities
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": "usda-fdc-mcp",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "tools/list":
        # Return list of available tools
        tools = [
            {
                "name": "get_food",
                "description": "Get details for a single food item by FDC ID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "fdc_id": {"type": "string", "description": "The FDC ID of the food item"},
                        "format_type": {"type": "string", "enum": ["abridged", "full"], "default": "full", "description": "Format of the response"},
                        "nutrients": {"type": "array", "items": {"type": "integer"}, "description": "List of nutrient IDs to include"}
                    },
                    "required": ["fdc_id"]
                }
            },
            {
                "name": "get_foods",
                "description": "Get details for multiple food items by FDC IDs.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "fdc_ids": {"type": "array", "items": {"type": "string"}, "description": "List of FDC IDs"},
                        "format_type": {"type": "string", "enum": ["abridged", "full"], "default": "full"},
                        "nutrients": {"type": "array", "items": {"type": "integer"}}
                    },
                    "required": ["fdc_ids"]
                }
            },
            {
                "name": "search_foods",
                "description": "Search for foods using keywords.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "data_type": {"type": "array", "items": {"type": "string"}, "description": "Data types to search"},
                        "page_size": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                        "page_number": {"type": "integer", "default": 1, "minimum": 1},
                        "sort_by": {"type": "string"},
                        "sort_order": {"type": "string", "enum": ["asc", "desc"]},
                        "brand_owner": {"type": "string"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "list_foods",
                "description": "Get a paged list of foods.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "data_type": {"type": "array", "items": {"type": "string"}},
                        "page_size": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                        "page_number": {"type": "integer", "default": 1, "minimum": 1},
                        "sort_by": {"type": "string"},
                        "sort_order": {"type": "string", "enum": ["asc", "desc"]}
                    }
                }
            }
        ]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools}
        }

    elif method == "tools/call":
        # Call a tool
        tool_name = params.get("name")
        args = params.get("arguments") or {}

        mapping = {
            "get_food": get_food,
            "get_foods": get_foods,
            "search_foods": search_foods,
            "list_foods": list_foods,
        }

        if tool_name not in mapping:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}

        fn = mapping[tool_name]

        try:
            result = await fn(**args) if asyncio.iscoroutinefunction(fn) else fn(**args)
            # Wrap result in MCP content format for compatibility
            if isinstance(result, str):
                content = [{"type": "text", "text": result}]
            else:
                content = [{"type": "text", "text": json.dumps(result)}]
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": content}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}}

    else:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}
