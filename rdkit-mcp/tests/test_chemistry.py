import pytest
from rdkit import Chem

from rdkit_mcp import chemistry

VANILLIN = "COc1cc(C=O)ccc1O"
ETHYL_VANILLIN = "CCOc1cc(C=O)ccc1O"
LIMONENE = "CC1=CCC(CC1)C(=C)C"
GLYCEROL = "OCC(O)CO"


@pytest.mark.parametrize(
    ("smiles", "formula", "expected_class"),
    [(GLYCEROL, "C3H8O3", "Water"), (VANILLIN, "C8H8O3", "Alcohol"), (LIMONENE, "C10H16", "Fat")],
)
def test_analyze_properties_classifies_solubility(smiles, formula, expected_class):
    result = chemistry.analyze_properties(smiles)

    assert result["molecular_formula"] == formula
    assert result["solubility_class"].startswith(expected_class)


def test_analyze_properties_values_for_vanillin():
    result = chemistry.analyze_properties(VANILLIN)

    assert result["molecular_weight"] == pytest.approx(152.15, abs=0.01)
    assert result["h_bond_donors"] == 1
    assert result["h_bond_acceptors"] == 3


@pytest.mark.parametrize("bad", ["", "   ", "not-a-molecule", "C1CC", "C" * (chemistry.MAX_SMILES_LENGTH + 1)])
def test_parse_smiles_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        chemistry.parse_smiles(bad)


def test_find_similar_ranks_and_reports_invalid():
    result = chemistry.find_similar(VANILLIN, [LIMONENE, ETHYL_VANILLIN, "garbage", VANILLIN], threshold=0.3)

    smiles = [m["smiles"] for m in result["matches"]]
    assert smiles[0] == VANILLIN
    assert result["matches"][0]["similarity"] == 1.0
    assert smiles[1] == ETHYL_VANILLIN
    assert LIMONENE not in smiles
    assert result["invalid_smiles"] == ["garbage"]


def test_find_similar_with_no_candidates():
    assert chemistry.find_similar(VANILLIN, [])["matches"] == []


def test_generate_3d_returns_valid_conformer():
    result = chemistry.generate_3d(VANILLIN)

    mol = Chem.MolFromMolBlock(result["mol_block"], removeHs=False)
    assert mol.GetNumConformers() == 1
    assert mol.GetConformer().Is3D()
    assert result["force_field"] == "MMFF94"


def test_generate_3d_rejects_huge_molecules():
    with pytest.raises(ValueError, match="heavy atoms"):
        chemistry.generate_3d("C" * (chemistry.MAX_HEAVY_ATOMS_3D + 1))


def test_draw_png_returns_png_bytes():
    assert chemistry.draw_png(VANILLIN, 200).startswith(b"\x89PNG")


def test_screen_properties_flags_large_lipophilic_molecules():
    result = chemistry.screen_properties("C" * 40)

    notes = " ".join(result["notes"])
    assert "High molecular weight" in notes
    assert "lipophilic" in notes
    assert 0 <= result["qed_score"] <= 1
    assert "GRAS" in result["disclaimer"]


def test_screen_properties_flags_aldehyde_alert():
    # QED counts aldehydes as a structural alert, so vanillin is flagged
    assert "structural alert" in chemistry.screen_properties(VANILLIN)["notes"][0]


def test_screen_properties_no_flags_for_caffeine():
    assert chemistry.screen_properties("Cn1cnc2c1c(=O)n(C)c(=O)n2C")["notes"] == ["No structural flags raised."]
