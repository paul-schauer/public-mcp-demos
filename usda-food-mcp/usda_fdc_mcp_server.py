#!/usr/bin/env python3
"""
USDA Food Data Central (FDC) MCP Server

This server provides access to the USDA Food Data Central API through MCP tools.
It allows searching for foods, getting detailed food information, and listing foods.
"""

import asyncio
import logging
from dotenv import load_dotenv
import os
from typing import Any, Dict, List, Optional, Union


import httpx
from mcp.server.fastmcp import FastMCP


# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("usda-fdc-mcp")

# API Configuration
BASE_URL = "https://api.nal.usda.gov/fdc"
API_VERSION = "v1"

# Initialize the MCP server
app = FastMCP("usda-fdc")

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


# Global FDC client instance
fdc_client: Optional[FDCAPIClient] = None





@app.tool()
async def get_food(fdc_id: str, format_type: str = "full", nutrients: Optional[List[int]] = None) -> Dict[str, Any]:
    """Get details for a single food item by FDC ID."""
    global fdc_client
    if fdc_client is None:
        raise Exception("FDC API client not initialized.")
    return await fdc_client.get_food(fdc_id, format_type, nutrients)

@app.tool()
async def get_foods(fdc_ids: List[str], format_type: str = "full", nutrients: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    """Get details for multiple food items by FDC IDs."""
    global fdc_client
    if fdc_client is None:
        raise Exception("FDC API client not initialized.")
    return await fdc_client.get_foods(fdc_ids, format_type, nutrients)

@app.tool()
async def search_foods(query: str, data_type: Optional[List[str]] = None, page_size: int = 50, page_number: int = 1, sort_by: Optional[str] = None, sort_order: Optional[str] = None, brand_owner: Optional[str] = None) -> Dict[str, Any]:
    """Search for foods using keywords."""
    print("search_foods called")
    global fdc_client
    if fdc_client is None:
        raise Exception("FDC API client not initialized.")
    return await fdc_client.search_foods(query, data_type, page_size, page_number, sort_by, sort_order, brand_owner)

@app.tool()
async def list_foods(data_type: Optional[List[str]] = None, page_size: int = 50, page_number: int = 1, sort_by: Optional[str] = None, sort_order: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get a paged list of foods."""
    global fdc_client
    if fdc_client is None:
        raise Exception("FDC API client not initialized.")
    return await fdc_client.list_foods(data_type, page_size, page_number, sort_by, sort_order)




def main():
    """Main entry point for the MCP server."""
    global fdc_client
    
    # Get API key from environment variable
    api_key = os.getenv("USDA_FDC_API_KEY")
    if not api_key:
        logger.error("USDA_FDC_API_KEY environment variable not set")
        logger.info("Please get your free API key from: https://fdc.nal.usda.gov/api-key-signup.html")
        exit(1)
    
    # Initialize the FDC client
    fdc_client = FDCAPIClient(api_key)
    
    # Run the server
    logger.info("Starting USDA Food Data Central MCP Server...")
    logger.info("Available tools: get_food, get_foods, search_foods, list_foods")
    
    app.run()


if __name__ == "__main__":
    main()
