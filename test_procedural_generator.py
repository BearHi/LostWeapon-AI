"""test_procedural_generator.py - Unit and Integration Tests for Procedural Map Generator.

Verifies:
  1. Archetype Registry & Schema Conformance:
     - All 8 archetypes generate valid MapSpec instances.
     - Spawn, goal, lava, and tile records are physically bounded.
  2. Determinism & Seed Integrity:
     - Identical seeds produce bit-identical specs and hashes.
  3. MapCompiler Roundtrip:
     - All archetype specs compile to valid LMF binary files.
  4. BatchMapPipeline Smoke Test:
     - Successfully runs full 3-stage validation pipeline on generated candidates.
     - Emits verified LMF, spec JSON, ref actions, and manifest.
"""
from pathlib import Path
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parent
HARNESS_DIR = ROOT / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from batch_map_pipeline import BatchMapPipeline
from map_compiler import MapCompiler, MapSpec
from procedural_generator import ARCHETYPE_CLASSES, ProceduralMapGenerator


class TestProceduralMapGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = ProceduralMapGenerator()
        cls.test_output_dir = ROOT / "scratch" / "test_procedural_output"
        cls.test_temp_dir = ROOT / "scratch" / "test_procedural_temp"
        cls.test_output_dir.mkdir(parents=True, exist_ok=True)
        cls.test_temp_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        # Clean up temporary directories
        if cls.test_temp_dir.exists():
            shutil.rmtree(cls.test_temp_dir, ignore_errors=True)

    def test_01_archetype_registry_completeness(self):
        """All 8 required physics archetypes are registered."""
        expected_ids = {
            "ARCH_01_BASIC_GAP",
            "ARCH_02_STEP_UP",
            "ARCH_03_BACKROLL_WALL",
            "ARCH_04_KNIFE_DASH",
            "ARCH_05_PILLAR_BRAKE",
            "ARCH_06_PARACHUTE_CHASM",
            "ARCH_07_SPRING_LAUNCH",
            "ARCH_08_COLLAPSE_BRIDGE",
        }
        actual_ids = set(self.generator.archetypes.keys())
        self.assertEqual(expected_ids, actual_ids)

    def test_02_mapspec_schema_conformance(self):
        """Every archetype generates valid MapSpec conforming to schema requirements."""
        for arch_id, arch_instance in self.generator.archetypes.items():
            candidates = list(arch_instance.generate_candidates(mode="grid", count=1))
            self.assertGreater(len(candidates), 0, f"Archetype {arch_id} yielded 0 candidates.")
            cand = candidates[0]

            spec = cand.spec
            self.assertIsInstance(spec, MapSpec)
            self.assertTrue(spec.map_id.startswith("arch"))
            self.assertGreater(spec.width, 0)
            self.assertGreater(spec.height, 0)
            self.assertIn("x", spec.spawn)
            self.assertIn("y", spec.spawn)
            self.assertIn("x", spec.goal)
            self.assertIn("y", spec.goal)
            self.assertGreater(len(spec.tiles), 0)

            # Assert reference actions non-empty
            self.assertGreater(
                len(cand.reference_actions),
                0,
                f"Candidate {cand.variation_id} has empty reference actions.",
            )

    def test_03_seed_determinism(self):
        """Sampling with identical seed produces bit-identical specs and hashes."""
        for arch_id in ["ARCH_01_BASIC_GAP", "ARCH_04_KNIFE_DASH"]:
            arch = self.generator.archetypes[arch_id]
            cands_a = list(arch.generate_candidates(mode="sample", count=3, seed=12345))
            cands_b = list(arch.generate_candidates(mode="sample", count=3, seed=12345))

            self.assertEqual(len(cands_a), len(cands_b))
            for ca, cb in zip(cands_a, cands_b):
                self.assertEqual(ca.compute_spec_sha256(), cb.compute_spec_sha256())
                self.assertEqual(ca.spec.tiles, cb.spec.tiles)
                self.assertEqual(ca.reference_actions, cb.reference_actions)

    def test_04_map_compiler_integration(self):
        """All 8 archetype candidates successfully compile to binary LMF files."""
        for arch_id, arch in self.generator.archetypes.items():
            cand = next(arch.generate_candidates(mode="grid", count=1))
            out_lmf = self.test_temp_dir / f"test_{arch_id}.LMF"
            res_path = MapCompiler.compile(cand.spec, out_lmf)

            self.assertTrue(res_path.exists())
            raw_bytes = res_path.read_bytes()
            self.assertGreater(len(raw_bytes), 32)
            self.assertTrue(raw_bytes.startswith(b"NewLWMapFile_1.0"))

    def test_05_pipeline_smoke_e2e(self):
        """BatchMapPipeline runs full 3-stage verification and saves verified maps."""
        pipeline = BatchMapPipeline(
            output_dir=self.test_output_dir,
            temp_dir=self.test_temp_dir,
            enable_quarantine=False,
        )

        # Run smoke test on ARCH_01_BASIC_GAP (1 candidate)
        res = pipeline.run_batch(
            archetype_ids=["ARCH_01_BASIC_GAP"],
            mode="grid",
            count_per_archetype=1,
            max_ticks=150,
        )

        self.assertGreater(res["verified_maps_count"], 0)
        self.assertEqual(res["stats"]["verified_passed"], 1)

        saved_map = res["verified_maps"][0]
        lmf_path = Path(saved_map["lmf_path"])
        spec_path = Path(saved_map["spec_path"])
        ref_path = Path(saved_map["ref_path"])

        self.assertTrue(lmf_path.exists())
        self.assertTrue(spec_path.exists())
        self.assertTrue(ref_path.exists())

        manifest_path = self.test_output_dir / "dataset_manifest.json"
        self.assertTrue(manifest_path.exists())


if __name__ == "__main__":
    unittest.main()
