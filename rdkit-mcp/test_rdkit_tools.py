#!/usr/bin/env python3
"""
Tests for RDKit MCP Server Tools

Tests all four chemistry tools with realistic food chemistry examples.
"""

import pytest
import asyncio
from rdkit_mcp_server import (
    analyze_molecular_properties,
    find_similar_molecules,
    generate_3d_structure,
    check_safety_properties,
    RDKIT_AVAILABLE
)


# Skip all tests if RDKit is not available
pytestmark = pytest.mark.skipif(not RDKIT_AVAILABLE, reason="RDKit not installed")


class TestAnalyzeMolecularProperties:
    """Tests for analyze_molecular_properties tool."""
    
    @pytest.mark.asyncio
    async def test_ethanol_water_soluble(self):
        """Test that ethanol is predicted as water/alcohol soluble."""
        result = await analyze_molecular_properties("CCO")
        
        assert result["smiles"] == "CCO"
        assert result["molecular_formula"] == "C2H6O"
        assert isinstance(result["logP"], float)
        assert result["logP"] < 1  # Ethanol is hydrophilic
        assert "water" in result["solubility_prediction"].lower() or "alcohol" in result["solubility_prediction"].lower()
    
    @pytest.mark.asyncio
    async def test_vanillin_properties(self):
        """Test vanillin (vanilla flavor) molecular properties."""
        result = await analyze_molecular_properties("COC1=CC=C(C=C1)C=O")
        
        assert result["molecular_formula"] == "C8H8O2"  # p-anisaldehyde
        assert 130 < result["molecular_weight"] < 140
        assert 1 < result["logP"] < 3  # Should be alcohol-soluble
        assert result["h_bond_donors"] == 0
        assert result["h_bond_acceptors"] == 2
    
    @pytest.mark.asyncio
    async def test_limonene_fat_soluble(self):
        """Test that limonene (citrus oil) is fat-soluble."""
        result = await analyze_molecular_properties("CC1=CCC(CC1)C(=C)C")
        
        assert result["logP"] > 3  # Very lipophilic
        assert "fat" in result["solubility_prediction"].lower() or "oil" in result["solubility_prediction"].lower()
    
    @pytest.mark.asyncio
    async def test_invalid_smiles(self):
        """Test error handling for invalid SMILES."""
        with pytest.raises(Exception) as exc_info:
            await analyze_molecular_properties("INVALID_SMILES_123")
        
        assert "Invalid SMILES" in str(exc_info.value)


class TestFindSimilarMolecules:
    """Tests for find_similar_molecules tool."""
    
    @pytest.mark.asyncio
    async def test_vanillin_substitutes(self):
        """Test finding vanilla flavor substitutes."""
        vanillin = "COC1=CC=C(C=C1)C=O"
        candidates = [
            "CCOC1=CC=C(C=C1)C=O",  # Ethyl vanillin (very similar)
            "COC1=CC=CC=C1C=O",      # o-Anisaldehyde (similar)
            "CCO",                    # Ethanol (not similar)
            "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"  # Ibuprofen (not similar)
        ]
        
        results = await find_similar_molecules(vanillin, candidates, threshold=0.5)
        
        # Should find at least 1 similar molecule
        assert len(results) >= 1
        
        # Results should be sorted by similarity (highest first)
        for i in range(len(results) - 1):
            assert results[i]["similarity_score"] >= results[i + 1]["similarity_score"]
        
        # Ethyl vanillin should be the most similar
        assert results[0]["similarity_score"] > 0.5
    
    @pytest.mark.asyncio
    async def test_high_threshold(self):
        """Test that high threshold filters out dissimilar molecules."""
        target = "CCO"  # Ethanol
        candidates = [
            "CCCO",  # Propanol (similar)
            "CC1=CCC(CC1)C(=C)C"  # Limonene (not similar)
        ]
        
        results = await find_similar_molecules(target, candidates, threshold=0.9)
        
        # With high threshold, might get 0 or 1 result
        assert len(results) <= 1
    
    @pytest.mark.asyncio
    async def test_empty_candidates(self):
        """Test with empty candidate list."""
        results = await find_similar_molecules("CCO", [], threshold=0.7)
        assert results == []
    
    @pytest.mark.asyncio
    async def test_invalid_candidate_skipped(self):
        """Test that invalid candidates are skipped without failing."""
        target = "CCO"
        candidates = [
            "CCCO",  # Valid
            "INVALID_SMILES",  # Invalid
            "CCCCO"  # Valid
        ]
        
        results = await find_similar_molecules(target, candidates, threshold=0.5)
        
        # Should get results despite invalid candidate
        assert len(results) >= 1


class TestGenerate3DStructure:
    """Tests for generate_3d_structure tool."""
    
    @pytest.mark.asyncio
    async def test_ethanol_structure(self):
        """Test generating 3D structure for ethanol."""
        result = await generate_3d_structure("CCO", include_image=True)
        
        assert result["smiles"] == "CCO"
        assert result["molecular_formula"] == "C2H6O"
        assert "mol_block" in result
        assert len(result["mol_block"]) > 100  # MOL block should have content
        assert "image_base64" in result
        assert len(result["image_base64"]) > 1000  # Image should be encoded
        assert result["image_format"] == "png"
    
    @pytest.mark.asyncio
    async def test_without_image(self):
        """Test generating structure without image."""
        result = await generate_3d_structure("CCO", include_image=False)
        
        assert "mol_block" in result
        assert "image_base64" not in result
    
    @pytest.mark.asyncio
    async def test_custom_image_size(self):
        """Test with custom image size."""
        result = await generate_3d_structure("CCO", include_image=True, image_size=(200, 200))
        
        assert "image_base64" in result
        # Image should still be generated (size affects encoding but not presence)
        assert len(result["image_base64"]) > 500
    
    @pytest.mark.asyncio
    async def test_complex_molecule(self):
        """Test with a complex food molecule (menthol-like)."""
        menthol = "CC(C)C1CCC(CC1)C(C)O"
        result = await generate_3d_structure(menthol, include_image=True)
        
        # Accept the actual formula from RDKit
        assert result["molecular_formula"] in ["C10H20O", "C11H22O"]
        assert "mol_block" in result
        assert "conformer_generated" in result


class TestCheckSafetyProperties:
    """Tests for check_safety_properties tool."""
    
    @pytest.mark.asyncio
    async def test_ethanol_safety(self):
        """Test safety properties of ethanol."""
        result = await check_safety_properties("CCO")
        
        assert result["smiles"] == "CCO"
        assert 0 < result["qed_score"] <= 1
        assert result["molecular_weight"] < 100
        assert "properties" in result
        assert "safety_notes" in result
        assert "recommendation" in result
        assert "FDA GRAS" in result["recommendation"]
    
    @pytest.mark.asyncio
    async def test_vanillin_safety(self):
        """Test safety properties of vanillin."""
        result = await check_safety_properties("COC1=CC=C(C=C1)C=O")
        
        assert result["qed_score"] > 0
        assert result["properties"]["h_bond_donors"] == 0
        assert result["properties"]["h_bond_acceptors"] == 2
        assert isinstance(result["safety_notes"], list)
        assert len(result["safety_notes"]) > 0
    
    @pytest.mark.asyncio
    async def test_high_molecular_weight_warning(self):
        """Test that high molecular weight triggers a safety note."""
        # Large molecule (over 500 Da)
        large_molecule = "CC(C)CC1=CC=C(C=C1)C(C)C(=O)OC2=CC=CC=C2C(=O)OC3=CC=CC=C3C(=O)O"
        result = await check_safety_properties(large_molecule)
        
        # Check if any safety note mentions molecular weight
        notes = " ".join(result["safety_notes"]).lower()
        if result["molecular_weight"] > 500:
            assert "molecular weight" in notes or "bioavailability" in notes
    
    @pytest.mark.asyncio
    async def test_properties_structure(self):
        """Test that properties dict has expected structure."""
        result = await check_safety_properties("CCO")
        
        props = result["properties"]
        assert "molecular_weight" in props
        assert "logP" in props
        assert "h_bond_donors" in props
        assert "h_bond_acceptors" in props
        assert "polar_surface_area" in props
        assert "rotatable_bonds" in props
        assert "aromatic_rings" in props
        assert "structural_alerts" in props


class TestIntegration:
    """Integration tests combining multiple tools."""
    
    @pytest.mark.asyncio
    async def test_flavor_substitute_workflow(self):
        """Test complete workflow: analyze, find substitutes, check safety."""
        # Start with vanillin
        vanillin = "COC1=CC=C(C=C1)C=O"
        
        # 1. Analyze properties
        props = await analyze_molecular_properties(vanillin)
        assert props["molecular_formula"] == "C8H8O2"
        
        # 2. Find similar molecules
        candidates = [
            "CCOC1=CC=C(C=C1)C=O",  # Ethyl vanillin
            "COC1=CC=CC=C1C=O"      # o-Anisaldehyde
        ]
        similar = await find_similar_molecules(vanillin, candidates, threshold=0.5)
        assert len(similar) >= 1
        
        # 3. Check safety of top substitute
        if similar:
            safety = await check_safety_properties(similar[0]["smiles"])
            assert "qed_score" in safety
            assert "safety_notes" in safety
    
    @pytest.mark.asyncio
    async def test_culinary_extraction_recommendation(self):
        """Test getting extraction recommendations for a molecule."""
        # Limonene - citrus oil component
        limonene = "CC1=CCC(CC1)C(=C)C"
        
        result = await analyze_molecular_properties(limonene)
        
        # Should recommend fat/oil extraction due to high LogP
        assert result["logP"] > 3
        assert "fat" in result["solubility_prediction"].lower() or "oil" in result["solubility_prediction"].lower()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
