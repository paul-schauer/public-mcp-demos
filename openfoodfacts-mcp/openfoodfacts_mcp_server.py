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
    
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
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


def _extract_facet_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract relevant info from a facet item."""
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "url": item.get("url", ""),
        "products": item.get("products", 0),
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


# =============================================================================
# FACETS ENDPOINTS (Category 2)
# =============================================================================

VALID_FACET_TYPES = [
    "categories", "brands", "labels", "additives", "allergens", 
    "countries", "ingredients", "stores", "origins", "states",
    "packaging", "nutrition_grades", "nova_groups", "ecoscore_grades"
]


@app.tool()
async def list_facets(
    facet_type: str,
    page: int = 1,
    page_size: int = 24
) -> Dict[str, Any]:
    """
    List all values for a specific facet type (categories, brands, labels, etc.).
    
    Returns a paginated list of facet values with product counts.
    Note: Facet endpoints are rate-limited to 2 requests per minute.
    
    Args:
        facet_type: Type of facet to list. Valid values: categories, brands, labels, 
                    additives, allergens, countries, ingredients, stores, origins, 
                    states, packaging, nutrition_grades, nova_groups, ecoscore_grades
        page: Page number for pagination (default: 1)
        page_size: Number of results per page (default: 24)
    
    Returns:
        Dictionary containing list of facet values with product counts
    """
    logger.info(f"Listing facets: type={facet_type}, page={page}")
    
    if facet_type not in VALID_FACET_TYPES:
        raise ValueError(f"Invalid facet_type '{facet_type}'. Valid types: {', '.join(VALID_FACET_TYPES)}")
    
    try:
        endpoint = f"/{facet_type}.json"
        params = {"page": page, "page_size": page_size}
        data = await _make_request(endpoint, params)
        
        tags = data.get("tags", [])
        
        result = {
            "facet_type": facet_type,
            "count": data.get("count", len(tags)),
            "page": page,
            "tags": [_extract_facet_item(tag) for tag in tags[:page_size]],
        }
        
        logger.info(f"Retrieved {len(result['tags'])} {facet_type}")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error listing facets: {str(e)}")
        raise Exception(f"Failed to list facets: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error listing facets: {str(e)}")
        raise Exception(f"Failed to list facets: {str(e)}")


@app.tool()
async def get_products_by_facet(
    facet_type: str,
    facet_value: str,
    page: int = 1,
    page_size: int = 24
) -> Dict[str, Any]:
    """
    Get products that match a specific facet value.
    
    For example, get all products in a category, by a brand, with a specific label,
    or containing a specific additive.
    Note: Facet endpoints are rate-limited to 2 requests per minute.
    
    Args:
        facet_type: Type of facet. Valid values: category, brand, label, additive, 
                    allergen, country, ingredient, store, origin, state, packaging,
                    nutrition_grade, nova_group, ecoscore_grade
        facet_value: The facet value to filter by (e.g., "organic" for labels, 
                     "coca-cola" for brands, "breakfast-cereals" for categories)
        page: Page number for pagination (default: 1)
        page_size: Number of results per page (default: 24)
    
    Returns:
        Dictionary containing products matching the facet filter
    """
    logger.info(f"Getting products by facet: {facet_type}={facet_value}, page={page}")
    
    # Singular to endpoint mapping
    facet_endpoints = {
        "category": "category",
        "brand": "brand", 
        "label": "label",
        "additive": "additive",
        "allergen": "allergen",
        "country": "country",
        "ingredient": "ingredient",
        "store": "store",
        "origin": "origin",
        "state": "state",
        "packaging": "packaging",
        "nutrition_grade": "nutrition-grade",
        "nova_group": "nova-group",
        "ecoscore_grade": "ecoscore-grade",
    }
    
    if facet_type not in facet_endpoints:
        raise ValueError(f"Invalid facet_type '{facet_type}'. Valid types: {', '.join(facet_endpoints.keys())}")
    
    try:
        endpoint_path = facet_endpoints[facet_type]
        endpoint = f"/{endpoint_path}/{facet_value}.json"
        params = {"page": page, "page_size": page_size}
        data = await _make_request(endpoint, params)
        
        products = data.get("products", [])
        
        result = {
            "facet_type": facet_type,
            "facet_value": facet_value,
            "count": data.get("count", 0),
            "page": data.get("page", page),
            "page_size": data.get("page_size", page_size),
            "products": [_extract_product_summary(p) for p in products],
        }
        
        logger.info(f"Retrieved {len(products)} products for {facet_type}={facet_value}")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error getting products by facet: {str(e)}")
        raise Exception(f"Failed to get products by facet: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error getting products by facet: {str(e)}")
        raise Exception(f"Failed to get products by facet: {str(e)}")


@app.tool()
async def get_products_by_multiple_facets(
    facets: Dict[str, str],
    page: int = 1,
    page_size: int = 24
) -> Dict[str, Any]:
    """
    Get products matching multiple facet criteria simultaneously.
    
    Allows combining filters like category + label, ingredient + country, etc.
    For example: {"ingredient": "salt", "category": "breads"} to find breads with salt.
    Note: Facet endpoints are rate-limited to 2 requests per minute.
    
    Args:
        facets: Dictionary of facet_type: facet_value pairs to filter by.
                Example: {"category": "breakfast-cereals", "label": "organic"}
        page: Page number for pagination (default: 1)
        page_size: Number of results per page (default: 24)
    
    Returns:
        Dictionary containing products matching all facet filters
    """
    logger.info(f"Getting products by multiple facets: {facets}, page={page}")
    
    if not facets or len(facets) == 0:
        raise ValueError("At least one facet filter is required")
    
    facet_endpoints = {
        "category": "category",
        "brand": "brand",
        "label": "label",
        "additive": "additive",
        "allergen": "allergen",
        "country": "country",
        "ingredient": "ingredient",
        "store": "store",
        "origin": "origin",
        "state": "state",
    }
    
    try:
        # Build combined endpoint path
        path_parts = []
        for facet_type, facet_value in facets.items():
            if facet_type not in facet_endpoints:
                raise ValueError(f"Invalid facet_type '{facet_type}'. Valid types: {', '.join(facet_endpoints.keys())}")
            path_parts.append(f"{facet_endpoints[facet_type]}/{facet_value}")
        
        endpoint = "/" + "/".join(path_parts) + ".json"
        params = {"page": page, "page_size": page_size}
        data = await _make_request(endpoint, params)
        
        products = data.get("products", [])
        
        result = {
            "facets": facets,
            "count": data.get("count", 0),
            "page": data.get("page", page),
            "page_size": data.get("page_size", page_size),
            "products": [_extract_product_summary(p) for p in products],
        }
        
        logger.info(f"Retrieved {len(products)} products for combined facets")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error getting products by multiple facets: {str(e)}")
        raise Exception(f"Failed to get products by multiple facets: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error getting products by multiple facets: {str(e)}")
        raise Exception(f"Failed to get products by multiple facets: {str(e)}")


# =============================================================================
# BULK PRODUCT LOOKUP (Category 5)
# =============================================================================

@app.tool()
async def get_products_by_barcodes(
    barcodes: List[str],
    fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Fetch multiple products by their barcodes in a single request.
    
    More efficient than calling get_product_by_barcode multiple times.
    
    Args:
        barcodes: List of product barcodes to fetch (max 100)
        fields: Optional list of specific fields to return. If not provided, 
                returns standard summary fields. Examples: product_name, brands, 
                nutrition_grades, categories, nutriments, ingredients_text
    
    Returns:
        Dictionary containing list of products found and any not found
    """
    logger.info(f"Getting {len(barcodes)} products by barcodes")
    
    if not barcodes:
        raise ValueError("At least one barcode is required")
    
    if len(barcodes) > 100:
        raise ValueError("Maximum 100 barcodes per request")
    
    try:
        endpoint = f"/api/{OFF_API_VERSION}/search"
        
        # Join barcodes with commas
        codes_param = ",".join(barcodes)
        
        params = {"code": codes_param}
        
        if fields:
            params["fields"] = ",".join(["code"] + fields)
        else:
            params["fields"] = "code,product_name,brands,categories,nutriscore_grade,ecoscore_grade,nova_group,image_url"
        
        data = await _make_request(endpoint, params)
        
        products = data.get("products", [])
        found_codes = {p.get("code") for p in products}
        not_found = [code for code in barcodes if code not in found_codes]
        
        result = {
            "requested": len(barcodes),
            "found": len(products),
            "not_found_count": len(not_found),
            "not_found_barcodes": not_found,
            "products": [_extract_product_summary(p) for p in products] if not fields else products,
        }
        
        logger.info(f"Retrieved {len(products)} of {len(barcodes)} requested products")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching multiple products: {str(e)}")
        raise Exception(f"Failed to fetch products: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching multiple products: {str(e)}")
        raise Exception(f"Failed to get products by barcodes: {str(e)}")


# =============================================================================
# KNOWLEDGE PANELS FOR FACETS (Category 6)
# =============================================================================

FACETS_KP_API_BASE = "https://facets-kp.openfoodfacts.org"


@app.tool()
async def get_facet_knowledge_panel(
    facet_type: str,
    facet_value: str,
    language: str = "en"
) -> Dict[str, Any]:
    """
    Get knowledge panels for a specific facet (category, brand, label, etc.).
    
    Knowledge panels provide semi-structured educational/informational content
    about a facet value, useful for displaying to users.
    
    Args:
        facet_type: Type of facet. Valid values: category, brand, label, additive,
                    allergen, country, ingredient, origin
        facet_value: The facet tag value (e.g., "en:breakfast-cereals", "en:organic")
        language: Language code for the response (default: "en")
    
    Returns:
        Dictionary containing knowledge panels with structured information
    """
    logger.info(f"Getting knowledge panel for {facet_type}={facet_value}")
    
    valid_kp_facets = ["category", "brand", "label", "additive", "allergen", "country", "ingredient", "origin"]
    
    if facet_type not in valid_kp_facets:
        raise ValueError(f"Invalid facet_type '{facet_type}'. Valid types: {', '.join(valid_kp_facets)}")
    
    try:
        # Knowledge panels API uses a different base URL
        url = f"{FACETS_KP_API_BASE}/knowledge_panel"
        params = {
            "facet_tag": facet_type,
            "value_tag": facet_value,
            "lang_code": language,
        }
        
        headers = {"User-Agent": USER_AGENT}
        
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        result = {
            "facet_type": facet_type,
            "facet_value": facet_value,
            "language": language,
            "panels": data.get("knowledge_panels", data),
        }
        
        logger.info(f"Retrieved knowledge panel for {facet_type}={facet_value}")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching knowledge panel: {str(e)}")
        raise Exception(f"Failed to fetch knowledge panel: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching knowledge panel: {str(e)}")
        raise Exception(f"Failed to get facet knowledge panel: {str(e)}")


# =============================================================================
# TAXONOMY SUGGESTIONS (Part of Category 2)
# =============================================================================

@app.tool()
async def get_taxonomy_suggestions(
    tagtype: str,
    term: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Get autocomplete suggestions for taxonomy fields.
    
    Useful for building search interfaces with type-ahead suggestions
    for categories, brands, labels, ingredients, etc.
    
    Args:
        tagtype: Type of tag to get suggestions for. Valid values: categories, 
                 brands, labels, ingredients, additives, allergens, countries,
                 stores, origins, states, packaging_shapes, packaging_materials
        term: Search term to get suggestions for (prefix match)
        limit: Maximum number of suggestions to return (default: 10)
    
    Returns:
        Dictionary containing list of matching suggestions
    """
    logger.info(f"Getting taxonomy suggestions: tagtype={tagtype}, term={term}")
    
    valid_tagtypes = [
        "categories", "brands", "labels", "ingredients", "additives", 
        "allergens", "countries", "stores", "origins", "states",
        "packaging_shapes", "packaging_materials", "languages", "traces"
    ]
    
    if tagtype not in valid_tagtypes:
        raise ValueError(f"Invalid tagtype '{tagtype}'. Valid types: {', '.join(valid_tagtypes)}")
    
    try:
        endpoint = "/cgi/suggest.pl"
        params = {
            "tagtype": tagtype,
            "term": term,
            "limit": limit,
        }
        
        data = await _make_request(endpoint, params)
        
        # suggest.pl returns a simple list
        suggestions = data if isinstance(data, list) else []
        
        result = {
            "tagtype": tagtype,
            "term": term,
            "suggestions": suggestions[:limit],
        }
        
        logger.info(f"Retrieved {len(result['suggestions'])} suggestions for {tagtype}")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching suggestions: {str(e)}")
        raise Exception(f"Failed to fetch suggestions: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching suggestions: {str(e)}")
        raise Exception(f"Failed to get taxonomy suggestions: {str(e)}")


@app.tool()
async def advanced_search(
    categories_tags: Optional[str] = None,
    brands_tags: Optional[str] = None,
    labels_tags: Optional[str] = None,
    nutrition_grades_tags: Optional[str] = None,
    nova_groups_tags: Optional[str] = None,
    ecoscore_grades_tags: Optional[str] = None,
    allergens_tags: Optional[str] = None,
    countries_tags: Optional[str] = None,
    ingredients_tags: Optional[str] = None,
    additives_tags: Optional[str] = None,
    states_tags: Optional[str] = None,
    page: int = 1,
    page_size: int = 24,
    sort_by: str = "popularity",
    fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Advanced product search with multiple filter criteria.
    
    Allows filtering products by various tags like categories, brands, 
    nutrition grades, NOVA groups, allergens, etc.
    
    Args:
        categories_tags: Filter by category (e.g., "breakfast-cereals", "beverages")
        brands_tags: Filter by brand (e.g., "nestle", "coca-cola")
        labels_tags: Filter by label (e.g., "organic", "fair-trade")
        nutrition_grades_tags: Filter by Nutri-Score grade (a, b, c, d, e)
        nova_groups_tags: Filter by NOVA group (1, 2, 3, 4)
        ecoscore_grades_tags: Filter by Eco-Score grade (a, b, c, d, e)
        allergens_tags: Filter by allergen (e.g., "milk", "gluten", "nuts")
        countries_tags: Filter by country (e.g., "united-states", "france")
        ingredients_tags: Filter by ingredient
        additives_tags: Filter by additive (e.g., "e330", "e621")
        states_tags: Filter by product state (e.g., "complete", "to-be-completed")
        page: Page number for pagination (default: 1)
        page_size: Number of results per page (default: 24, max: 100)
        sort_by: Sort order (popularity, product_name, created_t, last_modified_t)
        fields: Specific fields to return (optional)
    
    Returns:
        Dictionary containing filtered products with metadata
    """
    logger.info(f"Advanced search with filters, page={page}")
    
    try:
        endpoint = f"/api/{OFF_API_VERSION}/search"
        
        params = {
            "page": page,
            "page_size": min(page_size, 100),
            "sort_by": sort_by,
            "json": 1,
        }
        
        # Add tag filters
        if categories_tags:
            params["categories_tags_en"] = categories_tags
        if brands_tags:
            params["brands_tags"] = brands_tags
        if labels_tags:
            params["labels_tags_en"] = labels_tags
        if nutrition_grades_tags:
            params["nutrition_grades_tags"] = nutrition_grades_tags
        if nova_groups_tags:
            params["nova_groups_tags"] = nova_groups_tags
        if ecoscore_grades_tags:
            params["ecoscore_grades_tags"] = ecoscore_grades_tags
        if allergens_tags:
            params["allergens_tags"] = allergens_tags
        if countries_tags:
            params["countries_tags_en"] = countries_tags
        if ingredients_tags:
            params["ingredients_tags_en"] = ingredients_tags
        if additives_tags:
            params["additives_tags"] = additives_tags
        if states_tags:
            params["states_tags"] = states_tags
        
        if fields:
            params["fields"] = ",".join(["code"] + fields)
        
        data = await _make_request(endpoint, params)
        
        products = data.get("products", [])
        
        result = {
            "count": data.get("count", 0),
            "page": data.get("page", page),
            "page_size": data.get("page_size", page_size),
            "page_count": data.get("page_count", 0),
            "products": [_extract_product_summary(p) for p in products] if not fields else products,
        }
        
        logger.info(f"Advanced search returned {len(products)} products out of {result['count']} total")
        return result
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error in advanced search: {str(e)}")
        raise Exception(f"Failed to search: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error in advanced search: {str(e)}")
        raise Exception(f"Failed to perform advanced search: {str(e)}")


def main():
    """Main entry point for the MCP server."""
    try:
        logger.info("Starting OpenFoodFacts MCP Server...")
        logger.info("Available tools: get_product_by_barcode, search_products, get_product_nutrition, get_product_ingredients, list_facets, get_products_by_facet, get_products_by_multiple_facets, get_products_by_barcodes, get_facet_knowledge_panel, get_taxonomy_suggestions, advanced_search")
        
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
            },
            {
                "name": "list_facets",
                "description": "List all values for a specific facet type (categories, brands, labels, additives, etc.). Rate-limited to 2 req/min.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "facet_type": {"type": "string", "enum": ["categories", "brands", "labels", "additives", "allergens", "countries", "ingredients", "stores", "origins", "states", "packaging", "nutrition_grades", "nova_groups", "ecoscore_grades"], "description": "Type of facet to list"},
                        "page": {"type": "integer", "minimum": 1, "default": 1, "description": "Page number"},
                        "page_size": {"type": "integer", "minimum": 1, "default": 24, "description": "Results per page"}
                    },
                    "required": ["facet_type"]
                }
            },
            {
                "name": "get_products_by_facet",
                "description": "Get products matching a specific facet value (e.g., all products in a category or by a brand). Rate-limited to 2 req/min.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "facet_type": {"type": "string", "enum": ["category", "brand", "label", "additive", "allergen", "country", "ingredient", "store", "origin", "state", "packaging", "nutrition_grade", "nova_group", "ecoscore_grade"], "description": "Type of facet"},
                        "facet_value": {"type": "string", "description": "The facet value to filter by (e.g., 'organic', 'coca-cola', 'breakfast-cereals')"},
                        "page": {"type": "integer", "minimum": 1, "default": 1, "description": "Page number"},
                        "page_size": {"type": "integer", "minimum": 1, "default": 24, "description": "Results per page"}
                    },
                    "required": ["facet_type", "facet_value"]
                }
            },
            {
                "name": "get_products_by_multiple_facets",
                "description": "Get products matching multiple facet criteria (e.g., category + label). Rate-limited to 2 req/min.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "facets": {"type": "object", "description": "Dictionary of facet_type: facet_value pairs (e.g., {\"category\": \"cereals\", \"label\": \"organic\"})"},
                        "page": {"type": "integer", "minimum": 1, "default": 1, "description": "Page number"},
                        "page_size": {"type": "integer", "minimum": 1, "default": 24, "description": "Results per page"}
                    },
                    "required": ["facets"]
                }
            },
            {
                "name": "get_products_by_barcodes",
                "description": "Fetch multiple products by their barcodes in a single request (max 100).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "barcodes": {"type": "array", "items": {"type": "string"}, "description": "List of product barcodes to fetch"},
                        "fields": {"type": "array", "items": {"type": "string"}, "description": "Optional specific fields to return"}
                    },
                    "required": ["barcodes"]
                }
            },
            {
                "name": "get_facet_knowledge_panel",
                "description": "Get knowledge panels with educational content for a specific facet (category, brand, label, etc.).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "facet_type": {"type": "string", "enum": ["category", "brand", "label", "additive", "allergen", "country", "ingredient", "origin"], "description": "Type of facet"},
                        "facet_value": {"type": "string", "description": "The facet tag value (e.g., 'en:breakfast-cereals')"},
                        "language": {"type": "string", "default": "en", "description": "Language code for the response"}
                    },
                    "required": ["facet_type", "facet_value"]
                }
            },
            {
                "name": "get_taxonomy_suggestions",
                "description": "Get autocomplete suggestions for taxonomy fields (categories, brands, labels, etc.).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tagtype": {"type": "string", "enum": ["categories", "brands", "labels", "ingredients", "additives", "allergens", "countries", "stores", "origins", "states", "packaging_shapes", "packaging_materials", "languages", "traces"], "description": "Type of tag to get suggestions for"},
                        "term": {"type": "string", "description": "Search term for prefix matching"},
                        "limit": {"type": "integer", "minimum": 1, "default": 10, "description": "Max number of suggestions"}
                    },
                    "required": ["tagtype", "term"]
                }
            },
            {
                "name": "advanced_search",
                "description": "Advanced product search with multiple filter criteria (categories, brands, nutrition grades, NOVA groups, allergens, etc.).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "categories_tags": {"type": "string", "description": "Filter by category"},
                        "brands_tags": {"type": "string", "description": "Filter by brand"},
                        "labels_tags": {"type": "string", "description": "Filter by label"},
                        "nutrition_grades_tags": {"type": "string", "description": "Filter by Nutri-Score (a,b,c,d,e)"},
                        "nova_groups_tags": {"type": "string", "description": "Filter by NOVA group (1,2,3,4)"},
                        "ecoscore_grades_tags": {"type": "string", "description": "Filter by Eco-Score (a,b,c,d,e)"},
                        "allergens_tags": {"type": "string", "description": "Filter by allergen"},
                        "countries_tags": {"type": "string", "description": "Filter by country"},
                        "ingredients_tags": {"type": "string", "description": "Filter by ingredient"},
                        "additives_tags": {"type": "string", "description": "Filter by additive (e.g., e330)"},
                        "states_tags": {"type": "string", "description": "Filter by product state"},
                        "page": {"type": "integer", "minimum": 1, "default": 1, "description": "Page number"},
                        "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 24, "description": "Results per page"},
                        "sort_by": {"type": "string", "enum": ["popularity", "product_name", "created_t", "last_modified_t"], "default": "popularity", "description": "Sort order"},
                        "fields": {"type": "array", "items": {"type": "string"}, "description": "Specific fields to return"}
                    },
                    "required": []
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
            "list_facets": list_facets,
            "get_products_by_facet": get_products_by_facet,
            "get_products_by_multiple_facets": get_products_by_multiple_facets,
            "get_products_by_barcodes": get_products_by_barcodes,
            "get_facet_knowledge_panel": get_facet_knowledge_panel,
            "get_taxonomy_suggestions": get_taxonomy_suggestions,
            "advanced_search": advanced_search,
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
