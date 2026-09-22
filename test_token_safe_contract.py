#!/usr/bin/env python3
"""
Test Token-Safe Contract & Infrastructure
1. AST Linter: Prohibits loop-level print() calls in sweep and heavy scripts.
2. Stress Test: Executes 100,000 line child process and verifies 100% redirection to disk (<4KB console).
3. Exit Code & Summary Integrity.
"""

import sys
import os
import ast
import json
import unittest
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNLOGS_DIR = ROOT / "runlogs"

class LoopPrintDetector(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.violations = []
        self._loop_depth = 0

    def visit_For(self, node):
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_While(self, node):
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_Call(self, node):
        if self._loop_depth > 0:
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                self.violations.append((self.filename, node.lineno, "print() called inside loop"))
        self.generic_visit(node)


class TestTokenSafeContract(unittest.TestCase):
    def setUp(self):
        RUNLOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.python_bin = sys.executable
        self.runner_script = ROOT / "tools" / "token_safe_runner.py"

    def test_01_ast_linter_no_loop_prints(self):
        """AST Linter: Disallow print() calls inside for/while loops in sweep scripts."""
        target_files = [
            ROOT / "scratch" / "find_w4_brake_success.py",
            ROOT / "scratch" / "verify_domain_and_topen.py",
            ROOT / "candidate_suite_verifier.py",
            ROOT / "x86_oracle_verifier.py"
        ]

        all_violations = []
        for file_path in target_files:
            if not file_path.exists():
                continue
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            tree = ast.parse(content, filename=str(file_path))
            detector = LoopPrintDetector(str(file_path.relative_to(ROOT)))
            detector.visit(tree)
            all_violations.extend(detector.violations)

        self.assertEqual(
            len(all_violations),
            0,
            f"Found forbidden loop-level print() calls:\n"
            + "\n".join(f"  {f}:{line} - {msg}" for f, line, msg in all_violations)
        )

    def test_02_stress_100k_lines_redirection(self):
        """Stress Test: 100,000 lines child stdout is completely redirected; parent console <= 4KB."""
        scratch_script = ROOT / "scratch" / "stress_100k_child.py"
        scratch_script.write_text(
            "import sys\n"
            "for i in range(100000):\n"
            "    sys.stdout.write(f'line_{i}\\n')\n",
            encoding="utf-8"
        )

        run_id = "test_stress_100k"
        cmd = [
            self.python_bin,
            str(self.runner_script),
            "--run-id", run_id,
            "--",
            self.python_bin,
            str(scratch_script)
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(ROOT)
        )

        # 1. Exit code preserved
        self.assertEqual(proc.returncode, 0, f"Stress run failed: {proc.stderr}")

        # 2. Parent console output strictly under 4KB (4096 bytes)
        parent_out_bytes = len(proc.stdout.encode("utf-8"))
        self.assertLessEqual(
            parent_out_bytes,
            4096,
            f"Parent console output exceeded 4KB budget: {parent_out_bytes} bytes"
        )
        self.assertIn("=== TOKEN-SAFE RUN COMPLETED ===", proc.stdout)
        self.assertIn("RUN_ID:       test_stress_100k", proc.stdout)

        # 3. Log file exists on disk and contains all 100,000 lines
        log_path = RUNLOGS_DIR / f"{run_id}.log"
        self.assertTrue(log_path.exists(), f"Log file missing: {log_path}")
        line_count = 0
        with open(log_path, "r", encoding="utf-8") as f:
            for _ in f:
                line_count += 1
        self.assertEqual(line_count, 100000, f"Expected 100,000 lines in log file, got {line_count}")

        # 4. Summary file properly created
        summary_path = RUNLOGS_DIR / f"{run_id}.summary.json"
        self.assertTrue(summary_path.exists(), f"Summary file missing: {summary_path}")
        with open(summary_path, "r", encoding="utf-8") as f:
            summary_data = json.load(f)
        self.assertEqual(summary_data["run_id"], run_id)
        self.assertEqual(summary_data["status"], "SUCCESS")
        self.assertEqual(summary_data["exit_code"], 0)
        self.assertEqual(summary_data["log_lines"], 100000)

    def test_03_exit_code_preservation(self):
        """Exit code preservation: Non-zero exit code propagated and recorded as FAILED."""
        fail_script = ROOT / "scratch" / "fail_child.py"
        fail_script.write_text("import sys\nsys.exit(42)\n", encoding="utf-8")

        run_id = "test_exit_code_42"
        cmd = [
            self.python_bin,
            str(self.runner_script),
            "--run-id", run_id,
            "--",
            self.python_bin,
            str(fail_script)
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(ROOT)
        )

        self.assertEqual(proc.returncode, 42, "Runner must preserve child exit code")
        summary_path = RUNLOGS_DIR / f"{run_id}.summary.json"
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        self.assertEqual(summary["exit_code"], 42)
        self.assertEqual(summary["status"], "FAILED")

    def test_04_structured_summary_loading(self):
        """Structured summary: Child-written summary metrics are loaded and surfaced."""
        custom_script = ROOT / "scratch" / "custom_summary_child.py"
        custom_script.write_text(
            "import os, json\n"
            "summary_path = os.environ.get('TOKEN_SAFE_SUMMARY_PATH')\n"
            "with open(summary_path, 'w', encoding='utf-8') as f:\n"
            "    json.dump({'trials': 500, 'success': 37, 'death': 452, 'timeout': 11}, f, indent=2)\n",
            encoding="utf-8"
        )

        run_id = "test_custom_summary"
        cmd = [
            self.python_bin,
            str(self.runner_script),
            "--run-id", run_id,
            "--",
            self.python_bin,
            str(custom_script)
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(ROOT)
        )

        self.assertEqual(proc.returncode, 0)
        self.assertIn("trials=500", proc.stdout)
        self.assertIn("success=37", proc.stdout)


if __name__ == "__main__":
    unittest.main()
