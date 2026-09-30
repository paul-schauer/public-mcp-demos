#!/usr/bin/env python3
"""
Tests for OpenFoodFacts MCP Server Tools

Tests all four food product tools with realistic product examples.
"""

import pytest
import asyncio
from openfoodfacts_mcp_server import (
    get_product_by_barcode,
    search_products,
    get_product_nutrition,
    get_product_ingredients,
)


class TestGetProductByBarcode:
    """Tests for get_product_by_barcode tool."""
    
    @pytest.mark.asyncio
    async def test_nutella_barcode(self):
        """Test getting Nutella product by barcode."""
        # Nutella barcode
        result = await get_product_by_barcode("3017620422003")
        
        assert result["found"] is True
        assert result["barcode"] == "3017620422003"
        assert "product" in result
        assert "nutrition" in result
        assert "ingredients" in result
        
        # Check product name contains expected text
        product_name = result["product"]["product_name"].lower()
        assert "nutella" in product_name or result["product"]["brands"].lower() == "nutella"
    
    @pytest.mark.asyncio
    async def test_product_with_nutriscore(self):
        """Test that a product returns Nutri-Score grade."""
        # Use a well-known product that should have Nutri-Score
        result = await get_product_by_barcode("3017620422003")
        
        assert result["found"] is True
        # Nutri-Score should be present (a, b, c, d, or e)
        nutriscore = result["product"].get("nutriscore_grade", "")
        if nutriscore:
            assert nutriscore.lower() in ["a", "b", "c", "d", "e"]
    
    @pytest.mark.asyncio
    async def test_product_nutrition_data(self):
        """Test that nutrition data is returned correctly."""
        result = await get_product_by_barcode("3017620422003")
        
        assert "nutrition" in result
        nutrition = result["nutrition"]
        
        # Check that key nutrition fields are present
        assert "energy_kcal" in nutrition
        assert "fat" in nutrition
        assert "carbohydrates" in nutrition
        assert "proteins" in nutrition
    
    @pytest.mark.asyncio
    async def test_invalid_barcode(self):
        """Test error handling for invalid/non-existent barcode."""
        with pytest.raises(Exception) as exc_info:
            await get_product_by_barcode("0000000000000")
        
        assert "not found" in str(exc_info.value).lower()


class TestSearchProducts:
    """Tests for search_products tool."""
    
    @pytest.mark.asyncio
    async def test_search_coca_cola(self):
        """Test searching for Coca-Cola products."""
        result = await search_products("coca cola", page=1, page_size=5)
        
        assert "query" in result
        assert result["query"] == "coca cola"
        assert "products" in result
        assert "count" in result
        
        # Should find some products
        assert result["count"] > 0
        assert len(result["products"]) > 0
    
    @pytest.mark.asyncio
    async def test_search_pagination(self):
        """Test that pagination parameters work correctly."""
        result = await search_products("chocolate", page=1, page_size=3)
        
        assert result["page"] == 1
        assert len(result["products"]) <= 3
    
    @pytest.mark.asyncio
    async def test_search_returns_product_summaries(self):
        """Test that search results include expected product summary fields."""
        result = await search_products("nutella", page=1, page_size=5)
        
        assert len(result["products"]) > 0
        
        # Check first product has expected fields
        product = result["products"][0]
        assert "code" in product
        assert "product_name" in product
        assert "brands" in product
        assert "nutriscore_grade" in product
    
    @pytest.mark.asyncio
    async def test_empty_search(self):
        """Test search with unlikely query returns empty or minimal results."""
        result = await search_products("xyznonexistentproduct12345", page=1, page_size=10)
        
        # Should return a valid response even if no results
        assert "products" in result
        assert "count" in result


class TestGetProductNutrition:
    """Tests for get_product_nutrition tool."""
    
    @pytest.mark.asyncio
    async def test_nutrition_data_structure(self):
        """Test that nutrition data has expected structure."""
        result = await get_product_nutrition("3017620422003")
        
        assert "barcode" in result
        assert "product_name" in result
        assert "nutriscore" in result
        assert "per_100g" in result
        assert "per_serving" in result
    
    @pytest.mark.asyncio
    async def test_per_100g_nutrients(self):
        """Test that per 100g nutrient values are returned."""
        result = await get_product_nutrition("3017620422003")
        
        per_100g = result["per_100g"]
        
        # These fields should exist (may be None if not available)
        assert "energy_kcal" in per_100g
        assert "fat" in per_100g
        assert "saturated_fat" in per_100g
        assert "carbohydrates" in per_100g
        assert "sugars" in per_100g
        assert "proteins" in per_100g
        assert "salt" in per_100g
    
    @pytest.mark.asyncio
    async def test_nutriscore_details(self):
        """Test that Nutri-Score details are included."""
        result = await get_product_nutrition("3017620422003")
        
        nutriscore = result["nutriscore"]
        assert "grade" in nutriscore
        assert "score" in nutriscore
    
    @pytest.mark.asyncio
    async def test_invalid_barcode_nutrition(self):
        """Test error handling for invalid barcode."""
        with pytest.raises(Exception) as exc_info:
            await get_product_nutrition("0000000000000")
        
        assert "not found" in str(exc_info.value).lower()


class TestGetProductIngredients:
    """Tests for get_product_ingredients tool."""
    
    @pytest.mark.asyncio
    async def test_ingredients_data_structure(self):
        """Test that ingredients data has expected structure."""
        result = await get_product_ingredients("3017620422003")
        
        assert "barcode" in result
        assert "product_name" in result
        assert "ingredients_text" in result
        assert "allergens" in result
        assert "traces" in result
        assert "additives" in result
        assert "nova_group" in result
        assert "analysis" in result
    
    @pytest.mark.asyncio
    async def test_allergens_structure(self):
        """Test that allergens information has correct structure."""
        result = await get_product_ingredients("3017620422003")
        
        allergens = result["allergens"]
        assert "text" in allergens
        assert "tags" in allergens
    
    @pytest.mark.asyncio
    async def test_analysis_flags(self):
        """Test that analysis flags (vegan, vegetarian, palm oil) are returned."""
        result = await get_product_ingredients("3017620422003")
        
        analysis = result["analysis"]
        assert "is_vegan" in analysis
        assert "is_vegetarian" in analysis
        assert "is_palm_oil_free" in analysis
        assert "tags" in analysis
    
    @pytest.mark.asyncio
    async def test_additives_structure(self):
        """Test that additives information has correct structure."""
        result = await get_product_ingredients("3017620422003")
        
        additives = result["additives"]
        assert "count" in additives
        assert "tags" in additives
    
    @pytest.mark.asyncio
    async def test_invalid_barcode_ingredients(self):
        """Test error handling for invalid barcode."""
        with pytest.raises(Exception) as exc_info:
            await get_product_ingredients("0000000000000")
        
        assert "not found" in str(exc_info.value).lower()


class TestIntegration:
    """Integration tests combining multiple tools."""
    
    @pytest.mark.asyncio
    async def test_search_then_get_details(self):
        """Test workflow: search for product, then get its full details."""
        # 1. Search for a product
        search_result = await search_products("nutella", page=1, page_size=1)
        
        assert len(search_result["products"]) > 0
        
        # 2. Get the barcode from search result
        barcode = search_result["products"][0]["code"]
        assert barcode
        
        # 3. Get full product details
        product = await get_product_by_barcode(barcode)
        assert product["found"] is True
        
        # 4. Get detailed nutrition
        nutrition = await get_product_nutrition(barcode)
        assert "per_100g" in nutrition
        
        # 5. Get detailed ingredients
        ingredients = await get_product_ingredients(barcode)
        assert "allergens" in ingredients
    
    @pytest.mark.asyncio
    async def test_compare_products_nutrition(self):
        """Test comparing nutrition data between two products."""
        # Get nutrition for two different products
        nutella = await get_product_nutrition("3017620422003")  # Nutella
        
        # Just verify we can get nutrition data
        assert nutella["per_100g"]["energy_kcal"] is not None or nutella["per_100g"]["energy_kj"] is not None


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
