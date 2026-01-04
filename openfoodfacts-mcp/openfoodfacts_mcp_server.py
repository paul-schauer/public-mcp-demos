#!/usr/bin/env python3
"""
OpenFoodFacts MCP Server

This server provides food product information tools through the OpenFoodFacts API.
It allows looking up products by barcode, searching for products, and retrieving
nutritional information, Nutri-Score, and ingredient data.
"""

import sys
import asyncio
import json
import logging
import logging.handlers
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# Set up logging
logger = logging.getLogger("openfoodfacts-mcp")
logger.setLevel(logging.INFO)

# Configure logging to write to file only
file_handler = logging.handlers.RotatingFileHandler(
    'openfoodfacts_mcp.log',
    maxBytes=1024*1024,  # 1MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Prevent logging to stdout/stderr
logger.propagate = False

# Initialize the MCP server
app = FastMCP("openfoodfacts-mcp")

# OpenFoodFacts API configuration
OFF_API_BASE = "https://world.openfoodfacts.org"
OFF_API_VERSION = "v2"
USER_AGENT = "OpenFoodFactsMCP/1.0 (https://github.com/openfoodfacts/openfoodfacts-mcp)"

# HTTP client configuration
HTTP_TIMEOUT = 30.0


async def _make_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make a request to the OpenFoodFacts API."""
    url = f"{OFF_API_BASE}{endpoint}"
    headers = {"User-Agent": USER_AGENT}
    
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def _extract_product_summary(product: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a summary of useful product information."""
    return {
        "code": product.get("code", ""),
        "product_name": product.get("product_name", ""),
        "brands": product.get("brands", ""),
        "categories": product.get("categories", ""),
        "labels": product.get("labels", ""),
        "quantity": product.get("quantity", ""),
        "serving_size": product.get("serving_size", ""),
        "nutriscore_grade": product.get("nutriscore_grade", ""),
        "ecoscore_grade": product.get("ecoscore_grade", ""),
        "nova_group": product.get("nova_group", ""),
        "image_url": product.get("image_url", ""),
    }


def _extract_nutrition_info(product: Dict[str, Any]) -> Dict[str, Any]:
    """Extract nutrition information from a product."""
    nutriments = product.get("nutriments", {})
    
    return {
        "nutrition_data_per": product.get("nutrition_data_per", "100g"),
        "energy_kcal": nutriments.get("energy-kcal_100g"),
        "energy_kj": nutriments.get("energy-kj_100g"),
        "fat": nutriments.get("fat_100g"),
        "saturated_fat": nutriments.get("saturated-fat_100g"),
        "carbohydrates": nutriments.get("carbohydrates_100g"),
        "sugars": nutriments.get("sugars_100g"),
        "fiber": nutriments.get("fiber_100g"),
        "proteins": nutriments.get("proteins_100g"),
        "salt": nutriments.get("salt_100g"),
        "sodium": nutriments.get("sodium_100g"),
    }


def _extract_ingredients_info(product: Dict[str, Any]) -> Dict[str, Any]:
    """Extract ingredients information from a product."""
    return {
        "ingredients_text": product.get("ingredients_text", ""),
        "ingredients_count": len(product.get("ingredients", [])),
        "allergens": product.get("allergens", ""),
        "traces": product.get("traces", ""),
        "additives_tags": product.get("additives_tags", []),
        "ingredients_analysis_tags": product.get("ingredients_analysis_tags", []),
    }


@app.tool()
async def get_product_by_barcode(barcode: str) -> Dict[str, Any]:
    """
    Get detailed product information by barcode.
    
    Retrieves comprehensive information about a food product including:
    - Basic info (name, brand, categories, quantity)
    - Nutrition facts (energy, fat, carbs, proteins, etc.)
    - Nutri-Score and Eco-Score grades
    - NOVA group (food processing level)
    - Ingredients and allergens
    
    Args:
        barcode: The product barcode (EAN-13, UPC-A, etc.)
    
    Returns:
        Dictionary containing detailed product information
    """
    logger.info(f"Getting product by barcode: {barcode}")
    
    try:
        endpoint = f"/api/{OFF_API_VERSION}/product/{barcode}.json"
        data = await _make_request(endpoint)
        
        if data.get("status") != 1:
            raise ValueError(f"Product not found for barcode: {barcode}")
        
        product = data.get("product", {})
        
        result = {
            "found": True,
            "barcode": barcode,
            "product": _extract_product_summary(product),
            "nutrition": _extract_nutrition_info(product),
            "ingredients": _extract_ingredients_info(product),
        }
        
        logger.info(f"Found product: {product.get('product_name', 'Unknown')}")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching product: {str(e)}")
        raise Exception(f"Failed to fetch product: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching product: {str(e)}")
        raise Exception(f"Failed to get product by barcode: {str(e)}")


@app.tool()
async def search_products(
    query: str,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "popularity"
) -> Dict[str, Any]:
    """
    Search for food products by name, brand, or category.
    
    Search the OpenFoodFacts database for products matching your query.
    Results include basic product info and nutrition scores.
    
    Args:
        query: Search query (product name, brand, category, etc.)
        page: Page number for pagination (default: 1)
        page_size: Number of results per page (1-100, default: 10)
        sort_by: Sort order - "popularity", "product_name", "created_t", "last_modified_t" (default: "popularity")
    
    Returns:
        Dictionary containing search results with product summaries
    """
    logger.info(f"Searching products: query='{query}', page={page}, page_size={page_size}")
    
    try:
        # Clamp page_size to valid range
        page_size = max(1, min(100, page_size))
        
        endpoint = f"/cgi/search.pl"
        params = {
            "search_terms": query,
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "json": 1,
        }
        
        data = await _make_request(endpoint, params)
        
        products = data.get("products", [])
        
        result = {
            "query": query,
            "count": data.get("count", 0),
            "page": data.get("page", page),
            "page_size": data.get("page_size", page_size),
            "page_count": data.get("page_count", 0),
            "products": [_extract_product_summary(p) for p in products],
        }
        
        logger.info(f"Search returned {len(products)} products out of {result['count']} total")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error searching products: {str(e)}")
        raise Exception(f"Failed to search products: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error searching products: {str(e)}")
        raise Exception(f"Failed to search products: {str(e)}")


@app.tool()
async def get_product_nutrition(barcode: str) -> Dict[str, Any]:
    """
    Get detailed nutrition facts for a product by barcode.
    
    Returns comprehensive nutritional information including:
    - Energy (kcal and kJ)
    - Macronutrients (fat, carbohydrates, proteins)
    - Detailed breakdown (saturated fat, sugars, fiber, salt)
    - Nutri-Score grade and calculation details
    
    Args:
        barcode: The product barcode (EAN-13, UPC-A, etc.)
    
    Returns:
        Dictionary containing detailed nutrition information
    """
    logger.info(f"Getting nutrition for barcode: {barcode}")
    
    try:
        endpoint = f"/api/{OFF_API_VERSION}/product/{barcode}.json"
        params = {
            "fields": "code,product_name,brands,nutriments,nutriscore_grade,nutriscore_score,nutrition_grades,nutrition_data_per,serving_size,serving_quantity"
        }
        data = await _make_request(endpoint, params)
        
        if data.get("status") != 1:
            raise ValueError(f"Product not found for barcode: {barcode}")
        
        product = data.get("product", {})
        nutriments = product.get("nutriments", {})
        
        # Build comprehensive nutrition data
        result = {
            "barcode": barcode,
            "product_name": product.get("product_name", ""),
            "brands": product.get("brands", ""),
            "nutrition_data_per": product.get("nutrition_data_per", "100g"),
            "serving_size": product.get("serving_size", ""),
            "serving_quantity": product.get("serving_quantity"),
            "nutriscore": {
                "grade": product.get("nutriscore_grade", ""),
                "score": product.get("nutriscore_score"),
            },
            "per_100g": {
                "energy_kcal": nutriments.get("energy-kcal_100g"),
                "energy_kj": nutriments.get("energy-kj_100g"),
                "fat": nutriments.get("fat_100g"),
                "saturated_fat": nutriments.get("saturated-fat_100g"),
                "monounsaturated_fat": nutriments.get("monounsaturated-fat_100g"),
                "polyunsaturated_fat": nutriments.get("polyunsaturated-fat_100g"),
                "trans_fat": nutriments.get("trans-fat_100g"),
                "cholesterol": nutriments.get("cholesterol_100g"),
                "carbohydrates": nutriments.get("carbohydrates_100g"),
                "sugars": nutriments.get("sugars_100g"),
                "fiber": nutriments.get("fiber_100g"),
                "proteins": nutriments.get("proteins_100g"),
                "salt": nutriments.get("salt_100g"),
                "sodium": nutriments.get("sodium_100g"),
                "calcium": nutriments.get("calcium_100g"),
                "iron": nutriments.get("iron_100g"),
                "vitamin_a": nutriments.get("vitamin-a_100g"),
                "vitamin_c": nutriments.get("vitamin-c_100g"),
            },
            "per_serving": {
                "energy_kcal": nutriments.get("energy-kcal_serving"),
                "fat": nutriments.get("fat_serving"),
                "carbohydrates": nutriments.get("carbohydrates_serving"),
                "sugars": nutriments.get("sugars_serving"),
                "proteins": nutriments.get("proteins_serving"),
                "salt": nutriments.get("salt_serving"),
            }
        }
        
        logger.info(f"Retrieved nutrition for: {product.get('product_name', 'Unknown')}")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching nutrition: {str(e)}")
        raise Exception(f"Failed to fetch nutrition: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching nutrition: {str(e)}")
        raise Exception(f"Failed to get product nutrition: {str(e)}")


@app.tool()
async def get_product_ingredients(barcode: str) -> Dict[str, Any]:
    """
    Get detailed ingredients information for a product by barcode.
    
    Returns comprehensive ingredients data including:
    - Full ingredients list
    - Allergen information
    - Traces of allergens
    - Additives
    - NOVA group (food processing level)
    - Vegan/Vegetarian/Palm oil analysis
    
    Args:
        barcode: The product barcode (EAN-13, UPC-A, etc.)
    
    Returns:
        Dictionary containing detailed ingredients information
    """
    logger.info(f"Getting ingredients for barcode: {barcode}")
    
    try:
        endpoint = f"/api/{OFF_API_VERSION}/product/{barcode}.json"
        params = {
            "fields": "code,product_name,brands,ingredients_text,ingredients,allergens,allergens_tags,traces,traces_tags,additives_tags,additives_n,nova_group,ingredients_analysis_tags,ingredients_from_palm_oil_tags,labels_tags"
        }
        data = await _make_request(endpoint, params)
        
        if data.get("status") != 1:
            raise ValueError(f"Product not found for barcode: {barcode}")
        
        product = data.get("product", {})
        
        # Parse ingredient analysis tags
        analysis_tags = product.get("ingredients_analysis_tags", [])
        is_vegan = "en:vegan" in analysis_tags
        is_vegetarian = "en:vegetarian" in analysis_tags or is_vegan
        is_palm_oil_free = "en:palm-oil-free" in analysis_tags
        
        result = {
            "barcode": barcode,
            "product_name": product.get("product_name", ""),
            "brands": product.get("brands", ""),
            "ingredients_text": product.get("ingredients_text", ""),
            "ingredients_count": len(product.get("ingredients", [])),
            "ingredients_list": [
                {
                    "id": ing.get("id", ""),
                    "text": ing.get("text", ""),
                    "percent_estimate": ing.get("percent_estimate"),
                    "vegan": ing.get("vegan"),
                    "vegetarian": ing.get("vegetarian"),
                }
                for ing in product.get("ingredients", [])[:20]  # Limit to first 20
            ],
            "allergens": {
                "text": product.get("allergens", ""),
                "tags": product.get("allergens_tags", []),
            },
            "traces": {
                "text": product.get("traces", ""),
                "tags": product.get("traces_tags", []),
            },
            "additives": {
                "count": product.get("additives_n", 0),
                "tags": product.get("additives_tags", []),
            },
            "nova_group": product.get("nova_group"),
            "analysis": {
                "is_vegan": is_vegan,
                "is_vegetarian": is_vegetarian,
                "is_palm_oil_free": is_palm_oil_free,
                "tags": analysis_tags,
            },
            "labels": product.get("labels_tags", []),
        }
        
        logger.info(f"Retrieved ingredients for: {product.get('product_name', 'Unknown')}")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching ingredients: {str(e)}")
        raise Exception(f"Failed to fetch ingredients: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching ingredients: {str(e)}")
        raise Exception(f"Failed to get product ingredients: {str(e)}")


def main():
    """Main entry point for the MCP server."""
    try:
        logger.info("Starting OpenFoodFacts MCP Server...")
        logger.info("Available tools: get_product_by_barcode, search_products, get_product_nutrition, get_product_ingredients")
        
        # Run the server
        app.run('streamable-http')
        
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        print(f"[SERVER DEBUG] Server error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise


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
                    "name": "openfoodfacts-mcp",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "tools/list":
        # Return list of available tools
        tools = [
            {
                "name": "get_product_by_barcode",
                "description": "Get detailed product information by barcode including nutrition facts, Nutri-Score, ingredients, and allergens.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "barcode": {"type": "string", "description": "The product barcode (EAN-13, UPC-A, etc.)"}
                    },
                    "required": ["barcode"]
                }
            },
            {
                "name": "search_products",
                "description": "Search for food products by name, brand, or category. Returns product summaries with nutrition scores.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query (product name, brand, category, etc.)"},
                        "page": {"type": "integer", "minimum": 1, "default": 1, "description": "Page number for pagination"},
                        "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10, "description": "Number of results per page"},
                        "sort_by": {"type": "string", "enum": ["popularity", "product_name", "created_t", "last_modified_t"], "default": "popularity", "description": "Sort order for results"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_product_nutrition",
                "description": "Get detailed nutrition facts for a product including energy, macronutrients, vitamins, and Nutri-Score.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "barcode": {"type": "string", "description": "The product barcode (EAN-13, UPC-A, etc.)"}
                    },
                    "required": ["barcode"]
                }
            },
            {
                "name": "get_product_ingredients",
                "description": "Get detailed ingredients information including allergens, additives, NOVA group, and vegan/vegetarian analysis.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "barcode": {"type": "string", "description": "The product barcode (EAN-13, UPC-A, etc.)"}
                    },
                    "required": ["barcode"]
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
            "get_product_by_barcode": get_product_by_barcode,
            "search_products": search_products,
            "get_product_nutrition": get_product_nutrition,
            "get_product_ingredients": get_product_ingredients,
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


if __name__ == "__main__":
    main()
