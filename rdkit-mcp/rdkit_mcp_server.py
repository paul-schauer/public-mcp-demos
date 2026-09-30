#!/usr/bin/env python3
"""
RDKit MCP Server

This server provides molecular chemistry tools through RDKit for food chemistry applications.
It allows analyzing molecular properties, finding similar molecules, generating 3D structures,
and checking safety properties.
"""

import sys
import asyncio
import json
import logging
import logging.handlers
import base64
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from mcp.server.fastmcp import FastMCP

# Set up logging
logger = logging.getLogger("rdkit-mcp")
logger.setLevel(logging.INFO)

# Configure logging to write to file only
file_handler = logging.handlers.RotatingFileHandler(
    'rdkit_mcp.log',
    maxBytes=1024*1024,  # 1MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Prevent logging to stdout/stderr
logger.propagate = False

# Initialize the MCP server
app = FastMCP("rdkit-mcp")

# Import RDKit with error handling
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Crippen, Descriptors, QED, DataStructs, Draw
    RDKIT_AVAILABLE = True
    logger.info("RDKit successfully imported")
except ImportError as e:
    RDKIT_AVAILABLE = False
    logger.error(f"Failed to import RDKit: {e}")
    logger.error("Please install RDKit: pip install rdkit-pypi")


def _check_rdkit():
    """Check if RDKit is available and raise error if not."""
    if not RDKIT_AVAILABLE:
        raise Exception("RDKit is not available. Please install it with: pip install rdkit-pypi")


def _parse_smiles(smiles: str) -> Any:
    """Parse a SMILES string and return a molecule object."""
    _check_rdkit()
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES string: {smiles}")
    return mol


def _predict_solubility(logp: float) -> str:
    """Predict solubility category based on LogP value."""
    if logp < 0:
        return "Water-soluble (hydrophilic). Best for: syrups, brines, aqueous extractions"
    elif logp <= 3:
        return "Alcohol-soluble (amphiphilic). Best for: tinctures, high-proof extractions"
    else:
        return "Fat-soluble (lipophilic). Best for: oil infusions, fat-washing, lipid extractions"


@app.tool()
async def analyze_molecular_properties(smiles: str) -> Dict[str, Any]:
    """
    Analyze molecular properties of a compound from its SMILES string.
    
    Returns key properties including:
    - LogP (partition coefficient) for solubility prediction
    - Molecular weight
    - Number of hydrogen bond donors and acceptors
    - Topological polar surface area
    - Solubility prediction for culinary applications
    
    Args:
        smiles: SMILES string representation of the molecule (e.g., "CCO" for ethanol)
    
    Returns:
        Dictionary containing molecular properties and solubility predictions
    """
    logger.info(f"Analyzing molecular properties for SMILES: {smiles}")
    
    try:
        mol = _parse_smiles(smiles)
        
        # Calculate properties
        logp = Crippen.MolLogP(mol)
        mol_weight = Descriptors.MolWt(mol)
        h_bond_donors = Descriptors.NumHDonors(mol)
        h_bond_acceptors = Descriptors.NumHAcceptors(mol)
        tpsa = Descriptors.TPSA(mol)
        rotatable_bonds = Descriptors.NumRotatableBonds(mol)
        
        # Get solubility prediction
        solubility_prediction = _predict_solubility(logp)
        
        result = {
            "smiles": smiles,
            "logP": round(logp, 2),
            "molecular_weight": round(mol_weight, 2),
            "h_bond_donors": h_bond_donors,
            "h_bond_acceptors": h_bond_acceptors,
            "topological_polar_surface_area": round(tpsa, 2),
            "rotatable_bonds": rotatable_bonds,
            "solubility_prediction": solubility_prediction,
            "molecular_formula": Chem.rdMolDescriptors.CalcMolFormula(mol)
        }
        
        logger.info(f"Analysis complete: LogP={logp:.2f}, MW={mol_weight:.2f}")
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing molecule: {str(e)}")
        raise Exception(f"Failed to analyze molecular properties: {str(e)}")


@app.tool()
async def find_similar_molecules(
    target_smiles: str,
    candidate_smiles_list: List[str],
    threshold: float = 0.7
) -> List[Dict[str, Any]]:
    """
    Find molecules similar to a target molecule using Tanimoto similarity.
    
    Useful for finding flavor substitutes or structurally similar compounds.
    Uses Morgan fingerprints for similarity comparison.
    
    Args:
        target_smiles: SMILES string of the target molecule
        candidate_smiles_list: List of SMILES strings to compare against
        threshold: Minimum similarity score (0-1) to include in results (default: 0.7)
    
    Returns:
        List of similar molecules with similarity scores, sorted by similarity
    """
    logger.info(f"Finding molecules similar to: {target_smiles}")
    logger.info(f"Comparing against {len(candidate_smiles_list)} candidates")
    
    try:
        target_mol = _parse_smiles(target_smiles)
        target_fp = AllChem.GetMorganFingerprintAsBitVect(target_mol, 2, nBits=2048)
        
        results = []
        
        for candidate_smiles in candidate_smiles_list:
            try:
                candidate_mol = _parse_smiles(candidate_smiles)
                candidate_fp = AllChem.GetMorganFingerprintAsBitVect(candidate_mol, 2, nBits=2048)
                
                similarity = DataStructs.TanimotoSimilarity(target_fp, candidate_fp)
                
                if similarity >= threshold:
                    results.append({
                        "smiles": candidate_smiles,
                        "similarity_score": round(similarity, 4),
                        "molecular_formula": Chem.rdMolDescriptors.CalcMolFormula(candidate_mol),
                        "molecular_weight": round(Descriptors.MolWt(candidate_mol), 2)
                    })
                    
            except Exception as e:
                logger.warning(f"Error processing candidate {candidate_smiles}: {str(e)}")
                continue
        
        # Sort by similarity (highest first)
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        logger.info(f"Found {len(results)} similar molecules above threshold {threshold}")
        return results
        
    except Exception as e:
        logger.error(f"Error finding similar molecules: {str(e)}")
        raise Exception(f"Failed to find similar molecules: {str(e)}")


@app.tool()
async def generate_3d_structure(
    smiles: str,
    include_image: bool = True,
    image_size: Tuple[int, int] = (400, 400)
) -> Dict[str, Any]:
    """
    Generate a 3D structure of a molecule from its SMILES string.
    
    Can return:
    - MOL block (text format for 3D coordinates)
    - 2D structure image (base64 encoded PNG)
    
    Useful for visualization, labels, or educational materials.
    
    Args:
        smiles: SMILES string of the molecule
        include_image: Whether to generate a 2D structure image (default: True)
        image_size: Size of the generated image as (width, height) tuple
    
    Returns:
        Dictionary containing MOL block and optionally base64-encoded image
    """
    logger.info(f"Generating 3D structure for: {smiles}")
    
    try:
        mol = _parse_smiles(smiles)
        
        # Generate 3D coordinates
        mol_with_h = Chem.AddHs(mol)
        embed_result = AllChem.EmbedMolecule(mol_with_h, randomSeed=42)
        
        if embed_result != 0:
            logger.warning("3D embedding failed, using 2D coordinates")
            AllChem.Compute2DCoords(mol)
            mol_block = Chem.MolToMolBlock(mol)
            conformer_generated = False
        else:
            AllChem.MMFFOptimizeMolecule(mol_with_h)
            mol_block = Chem.MolToMolBlock(mol_with_h)
            conformer_generated = True
        
        result = {
            "smiles": smiles,
            "mol_block": mol_block,
            "conformer_generated": conformer_generated,
            "molecular_formula": Chem.rdMolDescriptors.CalcMolFormula(mol)
        }
        
        # Generate 2D structure image if requested
        if include_image:
            try:
                img = Draw.MolToImage(mol, size=image_size)
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                result["image_base64"] = img_str
                result["image_format"] = "png"
                logger.info("Generated 2D structure image")
            except Exception as e:
                logger.warning(f"Failed to generate image: {str(e)}")
                result["image_error"] = str(e)
        
        logger.info(f"3D structure generation complete (conformer: {conformer_generated})")
        return result
        
    except Exception as e:
        logger.error(f"Error generating 3D structure: {str(e)}")
        raise Exception(f"Failed to generate 3D structure: {str(e)}")


@app.tool()
async def check_safety_properties(smiles: str) -> Dict[str, Any]:
    """
    Check safety and drug-likeness properties using QED (Quantitative Estimate of Drug-likeness).
    
    While designed for drug-likeness, QED properties help identify potentially problematic
    compounds before using them in food applications:
    - Very low QED scores may indicate unstable or reactive compounds
    - Extreme molecular weights or polarities may indicate handling concerns
    - High number of alerts may indicate reactive functional groups
    
    This is a preliminary check - always verify with proper food safety databases.
    
    Args:
        smiles: SMILES string of the molecule
    
    Returns:
        Dictionary containing QED score and property breakdown with safety insights
    """
    logger.info(f"Checking safety properties for: {smiles}")
    
    try:
        mol = _parse_smiles(smiles)
        
        # Calculate QED properties
        qed_props = QED.properties(mol)
        qed_score = QED.qed(mol)
        
        # Get molecular weight and LogP for additional context
        mol_weight = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        
        # Generate safety insights
        safety_notes = []
        
        if mol_weight > 500:
            safety_notes.append("High molecular weight - may have poor bioavailability")
        if mol_weight < 50:
            safety_notes.append("Very low molecular weight - may be volatile or reactive")
        
        if logp > 5:
            safety_notes.append("Very lipophilic - may accumulate in fatty tissues")
        elif logp < -2:
            safety_notes.append("Very hydrophilic - limited fat solubility")
        
        if qed_props.HBA > 10:
            safety_notes.append("Many hydrogen bond acceptors - may affect absorption")
        if qed_props.HBD > 5:
            safety_notes.append("Many hydrogen bond donors - potential for strong interactions")
        
        if qed_props.ALERTS > 0:
            safety_notes.append(f"Contains {qed_props.ALERTS} structural alert(s) - review for reactive groups")
        
        if not safety_notes:
            safety_notes.append("No immediate concerns identified from molecular structure")
        
        result = {
            "smiles": smiles,
            "qed_score": round(qed_score, 3),
            "molecular_weight": round(mol_weight, 2),
            "logP": round(logp, 2),
            "properties": {
                "molecular_weight": round(qed_props.MW, 2),
                "logP": round(qed_props.ALOGP, 2),
                "h_bond_donors": qed_props.HBD,
                "h_bond_acceptors": qed_props.HBA,
                "polar_surface_area": round(qed_props.PSA, 2),
                "rotatable_bonds": qed_props.ROTB,
                "aromatic_rings": qed_props.AROM,
                "structural_alerts": qed_props.ALERTS
            },
            "safety_notes": safety_notes,
            "recommendation": "Always verify with FDA GRAS list and proper food safety databases before use in food applications"
        }
        
        logger.info(f"Safety check complete: QED={qed_score:.3f}, Alerts={qed_props.ALERTS}")
        return result
        
    except Exception as e:
        logger.error(f"Error checking safety properties: {str(e)}")
        raise Exception(f"Failed to check safety properties: {str(e)}")


def main():
    """Main entry point for the MCP server."""
    try:
        logger.info("Starting RDKit MCP Server...")
        logger.info("Available tools: analyze_molecular_properties, find_similar_molecules, generate_3d_structure, check_safety_properties")
        
        # Check RDKit availability
        _check_rdkit()
        
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
                    "name": "rdkit-mcp",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "tools/list":
        # Return list of available tools
        tools = [
            {
                "name": "analyze_molecular_properties",
                "description": "Analyze molecular properties including LogP, molecular weight, and solubility predictions for culinary applications.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "smiles": {"type": "string", "description": "SMILES string representation of the molecule"}
                    },
                    "required": ["smiles"]
                }
            },
            {
                "name": "find_similar_molecules",
                "description": "Find structurally similar molecules using Tanimoto similarity. Useful for finding flavor substitutes.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target_smiles": {"type": "string", "description": "SMILES string of the target molecule"},
                        "candidate_smiles_list": {"type": "array", "items": {"type": "string"}, "description": "List of candidate SMILES strings"},
                        "threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.7, "description": "Minimum similarity score (0-1)"}
                    },
                    "required": ["target_smiles", "candidate_smiles_list"]
                }
            },
            {
                "name": "generate_3d_structure",
                "description": "Generate 3D molecular structure and optionally a 2D visualization image.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "smiles": {"type": "string", "description": "SMILES string of the molecule"},
                        "include_image": {"type": "boolean", "default": True, "description": "Whether to generate a 2D structure image"},
                        "image_size": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2, "default": [400, 400], "description": "Image size as [width, height]"}
                    },
                    "required": ["smiles"]
                }
            },
            {
                "name": "check_safety_properties",
                "description": "Check safety and drug-likeness properties using QED. Provides preliminary safety insights for food chemistry applications.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "smiles": {"type": "string", "description": "SMILES string of the molecule"}
                    },
                    "required": ["smiles"]
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
            "analyze_molecular_properties": analyze_molecular_properties,
            "find_similar_molecules": find_similar_molecules,
            "generate_3d_structure": generate_3d_structure,
            "check_safety_properties": check_safety_properties,
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
