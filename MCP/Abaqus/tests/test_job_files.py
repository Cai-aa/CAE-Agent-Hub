"""Offline job-file contracts; no Abaqus or MCP dependency is needed."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

FIXTURES = Path(__file__).parent / "fixtures"


class JobFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def inspect(self, name="Example", **kwargs):
        self.assertIsNotNone(importlib.util.find_spec("job_files"), "job-files reader is not implemented")
        return importlib.import_module("job_files").inspect_job_files(name, str(self.directory), **kwargs)

    def fixture(self, source, suffix):
        shutil.copyfile(FIXTURES / source, self.directory / ("Example" + suffix))

    def test_memory_error_is_not_hidden_by_leading_space(self):
        self.fixture("memory_failure.txt", ".msg")
        result = self.inspect()
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["analysis_completed"])
        self.assertEqual(result["error_count"], 3)
        self.assertIn("insufficient memory", result["diagnostics"][-3]["message"])
        self.assertEqual(result["diagnostics"][-3]["line"], 1)
        self.assertTrue(result["diagnostics"][-3]["path"].endswith("Example.msg"))

    def test_datacheck_is_not_a_completed_analysis(self):
        self.fixture("datacheck.txt", ".dat")
        result = self.inspect()
        self.assertEqual(result["state"], "data_check_completed")
        self.assertEqual(result["stage"], "data_check")
        self.assertFalse(result["analysis_completed"])
        self.assertEqual(result["warning_count"], 2)

    def test_success_sta_is_sufficient_without_a_log_file(self):
        self.fixture("completed_sta.txt", ".sta")
        result = self.inspect()
        self.assertEqual(result["state"], "completed")
        self.assertTrue(result["analysis_completed"])
        self.assertEqual(result["stage"], "analysis")
        self.assertEqual(result["files"]["log"]["state"], "missing")
        self.assertTrue(result["read_success"])

    def test_explicit_completion_marker_at_increment_zero_is_not_analysis_completion(self):
        path = self.directory / "Example.sta"
        path.write_text(
            " Abaqus/Explicit 2024\n"
            " SOLUTION PROGRESS\n"
            "              STEP     TOTAL      WALL      STABLE\n"
            "INCREMENT     TIME      TIME      TIME   INCREMENT\n"
            " 0  0.000E+00  0.000E+00  00:00:01  1.000E-07\n"
            " THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n"
        )
        self.assertEqual(self.inspect()["state"], "incomplete")
        self.fixture("datacheck.txt", ".dat")
        self.assertEqual(self.inspect()["state"], "data_check_completed")

    def test_explicit_completion_marker_after_progress_counts_as_analysis_completion(self):
        (self.directory / "Example.sta").write_text(
            " Abaqus/Explicit 2024\n"
            " SOLUTION PROGRESS\n"
            "              STEP     TOTAL      WALL      STABLE\n"
            "INCREMENT     TIME      TIME      TIME   INCREMENT\n"
            " 0  0.000E+00  0.000E+00  00:00:01  1.000E-07\n"
            " 7  1.000E-03  1.000E-03  00:00:02  1.000E-07\n"
            " THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n"
        )
        self.fixture("datacheck.txt", ".dat")
        self.assertEqual(self.inspect()["state"], "completed")

    def test_missing_files_do_not_mean_a_successful_job(self):
        result = self.inspect()
        self.assertEqual(result["state"], "unknown")
        self.assertIsNone(result["analysis_completed"])
        self.assertTrue(all(f["state"] == "missing" for f in result["files"].values()))

    def test_partial_sta_and_lock_do_not_prove_a_live_process(self):
        (self.directory / "Example.sta").write_text(" STEP INC ATT SEVERE EQUIL TOTAL TIME\n 1 2 1 0 1 1 0.1\n")
        (self.directory / "Example.lck").touch()
        result = self.inspect()
        self.assertEqual(result["state"], "incomplete")
        self.assertTrue(result["lock_file_present"])
        self.assertIsNone(result["analysis_completed"])

    def test_same_name_in_different_directories_is_isolated(self):
        self.fixture("completed_sta.txt", ".sta")
        other = self.directory / "other"
        other.mkdir()
        (other / "Example.msg").write_text(" ***ERROR: input error\n")
        self.assertEqual(self.inspect()["state"], "completed")
        module = importlib.import_module("job_files")
        self.assertEqual(module.inspect_job_files("Example", str(other))["state"], "failed")

    def test_explicit_encoding_and_decode_failures_are_visible(self):
        path = self.directory / "Example.dat"
        path.write_bytes(" ***WARNING: 中文诊断\nANALYSIS DATACHECK COMPLETE\n".encode("gb18030"))
        result = self.inspect()
        self.assertFalse(result["read_success"])
        self.assertEqual(result["files"]["dat"]["state"], "read_error")
        self.assertIn("UnicodeDecodeError", result["read_errors"][0]["error"])
        decoded = self.inspect(encoding="gb18030")
        self.assertTrue(decoded["read_success"])
        self.assertIn("中文诊断", decoded["diagnostics"][0]["message"])
        self.assertEqual(decoded["state"], "data_check_completed")

    def test_unreadable_file_is_not_silently_empty(self):
        (self.directory / "Example.msg").mkdir()
        result = self.inspect()
        self.assertFalse(result["read_success"])
        self.assertEqual(result["files"]["msg"]["state"], "read_error")
        self.assertTrue(result["read_errors"])

    def test_wrapper_completed_line_alone_is_not_analysis_completion(self):
        (self.directory / "Example.log").write_text("Abaqus JOB Example COMPLETED\n")
        result = self.inspect()
        self.assertEqual(result["state"], "incomplete")
        self.assertIsNone(result["analysis_completed"])

    def test_failed_evidence_overrides_completed_message(self):
        self.fixture("completed_sta.txt", ".sta")
        (self.directory / "Example.log").write_text("Abaqus Error: solver exited with an error\n")
        result = self.inspect()
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["analysis_completed"])

    def test_analysis_attempt_after_preprocessing_datacheck_is_analysis_stage(self):
        self.fixture("datacheck.txt", ".dat")
        (self.directory / "Example.msg").write_text(
            " INCREMENT 1 STARTS. ATTEMPT NUMBER 1, TIME INCREMENT 0.005\n ***ERROR: solver failed\n"
        )
        result = self.inspect()
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["stage"], "analysis")

    def test_analysis_start_supersedes_preprocessing_datacheck_completion(self):
        self.fixture("datacheck.txt", ".dat")
        (self.directory / "Example.msg").write_text(
            " INCREMENT 1 STARTS. ATTEMPT NUMBER 1, TIME INCREMENT 0.005\n"
        )
        result = self.inspect()
        self.assertEqual(result["stage"], "analysis")
        self.assertEqual(result["state"], "incomplete")
        self.assertIsNone(result["analysis_completed"])

    def test_file_disappearing_between_stat_and_open_is_reported(self):
        target = self.directory / "Example.msg"
        target.touch()
        original = Path.open
        def disappearing(path, *args, **kwargs):
            if path == target:
                raise FileNotFoundError("file disappeared")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", disappearing):
            result = self.inspect()
        self.assertFalse(result["read_success"])
        self.assertEqual(result["files"]["msg"]["state"], "read_error")

    def test_error_before_later_decode_failure_remains_failure(self):
        self.fixture("completed_sta.txt", ".sta")
        (self.directory / "Example.msg").write_bytes(
            b" ***ERROR: known error before an unreadable later buffer\n"
            + b" ordinary progress line containing padding to fill buffers\n" * 600
            + b"\xff\n"
        )
        result = self.inspect()
        self.assertFalse(result["read_success"])
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["analysis_completed"])
        self.assertEqual(result["error_count"], 1)
        self.assertIn("known error", result["diagnostics"][0]["message"])
        self.assertTrue(result["files"]["msg"]["partial"])
        self.assertGreater(result["files"]["msg"]["line_count"], 0)

    def test_first_buffer_decode_failure_preserves_complete_error_line(self):
        self.fixture("completed_sta.txt", ".sta")
        content = b" ordinary first line\n ***ERROR: known error\n incomplete \xff tail\n"
        self.assertLess(len(content), 8192)
        (self.directory / "Example.msg").write_bytes(content)
        result = self.inspect()
        self.assertFalse(result["read_success"])
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["diagnostics"][0]["line"], 2)
        self.assertIn("known error", result["diagnostics"][0]["message"])
        self.assertEqual(result["files"]["msg"]["line_count"], 2)
        self.assertTrue(result["files"]["msg"]["partial"])
        self.assertIn("UnicodeDecodeError", result["read_errors"][0]["error"])

    def test_first_buffer_utf16_decode_failure_preserves_complete_error_line(self):
        self.fixture("completed_sta.txt", ".sta")
        (self.directory / "Example.sta").write_bytes(
            (FIXTURES / "completed_sta.txt").read_text().encode("utf-16")
        )
        (self.directory / "Example.msg").write_bytes(
            " ordinary first line\r\n ***ERROR: known UTF16 error\r\n incomplete ".encode("utf-16")
            + b"\x00\xd8A\x00"
        )
        result = self.inspect(encoding="utf-16")
        self.assertFalse(result["read_success"])
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["diagnostics"][0]["line"], 2)
        self.assertEqual(result["files"]["msg"]["line_count"], 2)
        self.assertTrue(result["files"]["msg"]["partial"])
        self.assertIn("UnicodeDecodeError", result["read_errors"][0]["error"])

    def test_gb18030_error_prefix_and_truncated_utf8_at_eof_are_preserved(self):
        for encoding, content in [
            ("gb18030", " ***ERROR: 中文错误\n".encode("gb18030") + b"\xff"),
            ("utf-8-sig", b" ***ERROR: truncated UTF8 later\n\xe4\xb8"),
        ]:
            with self.subTest(encoding=encoding):
                (self.directory / "Example.msg").write_bytes(content)
                result = self.inspect(encoding=encoding)
                self.assertFalse(result["read_success"])
                self.assertEqual(result["error_count"], 1)
                self.assertEqual(result["diagnostics"][0]["line"], 1)
                self.assertTrue(result["files"]["msg"]["partial"])

    def test_unterminated_line_before_bad_byte_is_not_counted_as_complete(self):
        (self.directory / "Example.msg").write_bytes(b" ***ERROR: incomplete header \xff\n")
        result = self.inspect()
        self.assertFalse(result["read_success"])
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["files"]["msg"]["line_count"], 0)

    def test_newline_variants_preserve_line_numbers_before_bad_bytes(self):
        for newline in (b"\n", b"\r", b"\r\n"):
            with self.subTest(newline=newline):
                (self.directory / "Example.msg").write_bytes(
                    b"first" + newline + b" ***ERROR: known" + newline + b"\xff"
                )
                result = self.inspect()
                self.assertFalse(result["read_success"])
                self.assertEqual(result["error_count"], 1)
                self.assertEqual(result["diagnostics"][0]["line"], 2)
                self.assertEqual(result["files"]["msg"]["line_count"], 2)

    def test_valid_multibyte_characters_and_newlines_cross_read_boundaries(self):
        for encoding in ("utf-8-sig", "gb18030", "utf-16"):
            with self.subTest(encoding=encoding):
                # Long valid text crosses binary read boundaries inside a
                # multibyte character and/or CRLF; no replacement is allowed.
                text = "first\r\n" + "中文" * 4095 + "\r\n ***ERROR: final line without newline"
                (self.directory / "Example.msg").write_bytes(text.encode(encoding))
                result = self.inspect(encoding=encoding)
                self.assertTrue(result["read_success"])
                self.assertEqual(result["error_count"], 1)
                self.assertEqual(result["diagnostics"][0]["line"], 3)
                self.assertEqual(result["files"]["msg"]["line_count"], 3)

    def test_error_before_later_io_failure_remains_failure(self):
        self.fixture("completed_sta.txt", ".sta")
        target = self.directory / "Example.msg"
        target.touch()
        original = Path.open
        class BrokenReader:
            read_once = False
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, size):
                if self.read_once:
                    raise OSError("disk read failed")
                self.read_once = True
                return b" ***ERROR: known error before I/O failure\n"
        def open_file(path, *args, **kwargs):
            return BrokenReader() if path == target else original(path, *args, **kwargs)
        with patch.object(Path, "open", open_file):
            result = self.inspect()
        self.assertFalse(result["read_success"])
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["error_count"], 1)
        self.assertTrue(result["files"]["msg"]["partial"])

    def test_sta_terminal_failure_without_msg_is_failed(self):
        (self.directory / "Example.sta").write_text(" THE ANALYSIS HAS NOT BEEN COMPLETED\n")
        result = self.inspect()
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["analysis_completed"])
        self.assertEqual(result["stage"], "analysis")
        self.assertTrue(result["terminal_failure_detected"])
        self.assertTrue(any(e["kind"] == "analysis_failed" for e in result["completion_evidence"]))

    def test_limit_bounds_tail_but_not_diagnostic_counts(self):
        (self.directory / "Example.msg").write_text(" ***WARNING: test\n" * 20)
        result = self.inspect(tail_lines=2, diagnostic_limit=3)
        self.assertEqual(result["warning_count"], 20)
        self.assertEqual(len(result["diagnostics"]), 3)
        self.assertEqual(len(result["files"]["msg"]["tail"]), 2)

    def test_path_traversal_and_invalid_limits_are_rejected(self):
        for name in ("../other", "other/job", "other\\job", "", ".", "..", "C:job"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.inspect(name)
        with self.assertRaises(ValueError):
            self.inspect(tail_lines=0)
        with self.assertRaises(ValueError):
            self.inspect(diagnostic_limit=10001)
        with self.assertRaises(ValueError):
            self.inspect(encoding="not-a-real-encoding")


if __name__ == "__main__":
    unittest.main()
