"""Cheminformatics helpers built on RDKit, framed for food and flavor chemistry.

Every function takes SMILES strings and returns plain JSON-serializable data, so the
MCP layer stays thin and this module can be tested on its own.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import QED, AllChem, Crippen, Descriptors, Draw, rdFingerprintGenerator, rdMolDescriptors

RDLogger.DisableLog("rdApp.*")  # RDKit otherwise prints parse errors to stderr, which corrupts stdio transport

MAX_SMILES_LENGTH = 1000
MAX_HEAVY_ATOMS_3D = 150
EMBED_TIMEOUT_SECONDS = 10

_morgan = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


def parse_smiles(smiles: str) -> Chem.Mol:
    """Parse a SMILES string, raising ``ValueError`` with a readable message if it's invalid."""
    smiles = smiles.strip()
    if not smiles:
        raise ValueError("SMILES string is empty")
    if len(smiles) > MAX_SMILES_LENGTH:
        raise ValueError(f"SMILES string is longer than {MAX_SMILES_LENGTH} characters")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES string: {smiles!r}")
    return mol


def solubility_class(logp: float) -> str:
    """Rough extraction-medium guide from Crippen LogP. A heuristic, not a measured solubility."""
    if logp < 0:
        return "Water-soluble (hydrophilic). Suits syrups, brines and aqueous extractions."
    if logp <= 3:
        return "Alcohol-soluble (amphiphilic). Suits tinctures and high-proof extractions."
    return "Fat-soluble (lipophilic). Suits oil infusions and fat-washing."


def analyze_properties(smiles: str) -> dict[str, Any]:
    mol = parse_smiles(smiles)
    logp = Crippen.MolLogP(mol)
    return {
        "smiles": Chem.MolToSmiles(mol),
        "molecular_formula": rdMolDescriptors.CalcMolFormula(mol),
        "molecular_weight": round(Descriptors.MolWt(mol), 2),
        "logP": round(logp, 2),
        "h_bond_donors": Descriptors.NumHDonors(mol),
        "h_bond_acceptors": Descriptors.NumHAcceptors(mol),
        "topological_polar_surface_area": round(Descriptors.TPSA(mol), 2),
        "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
        "solubility_class": solubility_class(logp),
    }


def find_similar(target_smiles: str, candidates: list[str], threshold: float = 0.7) -> dict[str, Any]:
    """Rank candidates by Tanimoto similarity of Morgan (ECFP4-like) fingerprints to the target."""
    target_fp = _morgan.GetFingerprint(parse_smiles(target_smiles))
    matches: list[dict[str, Any]] = []
    invalid: list[str] = []
    for smiles in candidates:
        try:
            mol = parse_smiles(smiles)
        except ValueError:
            invalid.append(smiles)
            continue
        score = DataStructs.TanimotoSimilarity(target_fp, _morgan.GetFingerprint(mol))
        if score >= threshold:
            matches.append(
                {
                    "smiles": smiles,
                    "similarity": round(score, 4),
                    "molecular_formula": rdMolDescriptors.CalcMolFormula(mol),
                    "molecular_weight": round(Descriptors.MolWt(mol), 2),
                }
            )
    matches.sort(key=lambda m: m["similarity"], reverse=True)
    return {"target": target_smiles, "threshold": threshold, "matches": matches, "invalid_smiles": invalid}


def generate_3d(smiles: str) -> dict[str, Any]:
    """Embed a 3D conformer with ETKDGv3 and relax it with MMFF, returning a MOL block."""
    mol = parse_smiles(smiles)
    if mol.GetNumHeavyAtoms() > MAX_HEAVY_ATOMS_3D:
        raise ValueError(f"3D generation is limited to {MAX_HEAVY_ATOMS_3D} heavy atoms")

    mol_h = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    params.timeout = EMBED_TIMEOUT_SECONDS
    if AllChem.EmbedMolecule(mol_h, params) != 0:
        raise ValueError("Could not generate a 3D conformer for this molecule")

    force_field = "MMFF94"
    if AllChem.MMFFHasAllMoleculeParams(mol_h):
        AllChem.MMFFOptimizeMolecule(mol_h, maxIters=500)
    else:
        AllChem.UFFOptimizeMolecule(mol_h, maxIters=500)
        force_field = "UFF"

    return {
        "smiles": Chem.MolToSmiles(mol),
        "molecular_formula": rdMolDescriptors.CalcMolFormula(mol),
        "force_field": force_field,
        "mol_block": Chem.MolToMolBlock(mol_h),
    }


def draw_png(smiles: str, size: int = 400) -> bytes:
    mol = parse_smiles(smiles)
    drawer = Draw.MolDraw2DCairo(size, size)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def screen_properties(smiles: str) -> dict[str, Any]:
    """Flag structural properties worth a closer look, using QED and simple thresholds.

    QED measures drug-likeness. It says nothing definitive about food safety, so the
    result is a prompt for further research, never a verdict.
    """
    mol = parse_smiles(smiles)
    props = QED.properties(mol)
    notes: list[str] = []
    if props.MW > 500:
        notes.append("High molecular weight (>500 Da), so likely poorly absorbed.")
    if props.MW < 50:
        notes.append("Very low molecular weight (<50 Da), so likely volatile.")
    if props.ALOGP > 5:
        notes.append("Very lipophilic (LogP > 5), so it may accumulate in fatty tissue.")
    elif props.ALOGP < -2:
        notes.append("Very hydrophilic (LogP < -2).")
    if props.ALERTS:
        notes.append(f"{props.ALERTS} structural alert(s): substructures often linked to reactivity or toxicity.")
    if not notes:
        notes.append("No structural flags raised.")

    return {
        "smiles": Chem.MolToSmiles(mol),
        "qed_score": round(QED.qed(mol), 3),
        "properties": {
            "molecular_weight": round(props.MW, 2),
            "logP": round(props.ALOGP, 2),
            "h_bond_donors": props.HBD,
            "h_bond_acceptors": props.HBA,
            "polar_surface_area": round(props.PSA, 2),
            "rotatable_bonds": props.ROTB,
            "aromatic_rings": props.AROM,
            "structural_alerts": props.ALERTS,
        },
        "notes": notes,
        "disclaimer": (
            "Computational screen only. Check regulatory sources such as the FDA GRAS "
            "inventory before using any compound in food."
        ),
    }
