"""Unit tests for :mod:`approval_tests_ir_datasets.comparison`: comparing an
approved result against a freshly computed one, type-dependently (see the
module's own docstring) -- integers/strings match exactly, floats match
within a small absolute tolerance, and dicts/lists recurse.
"""
from approval_tests_ir_datasets.comparison import (
    FLOAT_ABS_TOLERANCE,
    compare_results,
    diff,
    values_match,
)


class TestIntegers:
    def test_equal_integers_match(self) -> None:
        assert values_match(3, 3) is True

    def test_different_integers_do_not_match(self) -> None:
        assert values_match(3, 4) is False

    def test_integers_never_match_within_a_tolerance(self) -> None:
        # Unlike floats, an integer difference of even 1 is never "close
        # enough" -- exact match only.
        assert values_match(1000000, 1000001) is False


class TestStrings:
    def test_equal_strings_match(self) -> None:
        assert values_match("hello", "hello") is True

    def test_different_strings_do_not_match(self) -> None:
        assert values_match("hello", "Hello") is False

    def test_strings_are_case_sensitive(self) -> None:
        assert values_match("abc", "ABC") is False


class TestFloats:
    def test_equal_floats_match(self) -> None:
        assert values_match(0.5, 0.5) is True

    def test_floats_within_the_tolerance_match(self) -> None:
        assert values_match(0.34331265929286764, 0.34331269929286764) is True

    def test_floats_exactly_at_the_tolerance_boundary_match(self) -> None:
        assert values_match(1.0, 1.0 + FLOAT_ABS_TOLERANCE) is True

    def test_floats_beyond_the_tolerance_do_not_match(self) -> None:
        assert values_match(1.0, 1.0 + FLOAT_ABS_TOLERANCE * 10) is False

    def test_negative_floats_within_the_tolerance_match(self) -> None:
        assert values_match(-0.5, -0.50005) is True

    def test_int_and_float_are_compared_with_the_float_tolerance(self) -> None:
        # A JSON round-trip (or a verifier returning a plain int where it
        # happens to be a whole number) shouldn't itself count as a
        # difference -- only the numeric value matters once either side is
        # a float.
        assert values_match(3, 3.00001) is True

    def test_int_and_float_still_differ_beyond_the_tolerance(self) -> None:
        assert values_match(3, 3.1) is False


class TestBooleans:
    def test_equal_booleans_match(self) -> None:
        assert values_match(True, True) is True
        assert values_match(False, False) is True

    def test_different_booleans_do_not_match(self) -> None:
        assert values_match(True, False) is False

    def test_bool_never_matches_an_equal_looking_int(self) -> None:
        # Python's own `True == 1` would otherwise silently let a bool
        # field be "approved" against a differently-typed int field.
        assert values_match(True, 1) is False
        assert values_match(1, True) is False
        assert values_match(False, 0) is False


class TestNone:
    def test_none_matches_none(self) -> None:
        assert values_match(None, None) is True

    def test_none_does_not_match_a_value(self) -> None:
        assert values_match(None, 0) is False
        assert values_match(None, "") is False


class TestDicts:
    def test_identical_dicts_match(self) -> None:
        assert values_match({"a": 1, "b": "x"}, {"a": 1, "b": "x"}) is True

    def test_dicts_with_a_differing_value_do_not_match(self) -> None:
        assert values_match({"a": 1}, {"a": 2}) is False

    def test_dicts_with_a_missing_key_do_not_match(self) -> None:
        assert values_match({"a": 1, "b": 2}, {"a": 1}) is False

    def test_dicts_with_an_extra_key_do_not_match(self) -> None:
        assert values_match({"a": 1}, {"a": 1, "b": 2}) is False

    def test_key_order_does_not_matter(self) -> None:
        assert values_match({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True

    def test_nested_dicts_use_the_same_float_tolerance(self) -> None:
        assert values_match(
            {"metrics": {"nDCG@10": 0.34331265929286764}},
            {"metrics": {"nDCG@10": 0.34331269929286764}},
        ) is True

    def test_deeply_nested_mismatch_is_detected(self) -> None:
        assert values_match(
            {"a": {"b": {"c": 1}}}, {"a": {"b": {"c": 2}}}
        ) is False


class TestLists:
    def test_identical_lists_match(self) -> None:
        assert values_match([1, "a", 2.0], [1, "a", 2.0]) is True

    def test_lists_with_a_differing_element_do_not_match(self) -> None:
        assert values_match([1, 2, 3], [1, 2, 4]) is False

    def test_lists_of_different_length_do_not_match(self) -> None:
        assert values_match([1, 2], [1, 2, 3]) is False

    def test_list_order_matters(self) -> None:
        assert values_match([1, 2], [2, 1]) is False

    def test_lists_of_dicts_recurse(self) -> None:
        assert values_match(
            [{"a": 1}, {"a": 2.00001}], [{"a": 1}, {"a": 2.0}]
        ) is True


class TestDiffMessages:
    def test_matching_values_produce_no_differences(self) -> None:
        assert diff(3, 3) == []

    def test_a_mismatched_leaf_value_is_reported_with_its_path(self) -> None:
        differences = diff({"count": 3}, {"count": 4})
        assert len(differences) == 1
        assert "count" in differences[0]
        assert "3" in differences[0]
        assert "4" in differences[0]

    def test_a_missing_key_is_reported(self) -> None:
        differences = diff({"a": 1, "b": 2}, {"a": 1})
        assert len(differences) == 1
        assert "b" in differences[0]
        assert "missing" in differences[0]

    def test_an_unexpected_key_is_reported(self) -> None:
        differences = diff({"a": 1}, {"a": 1, "b": 2})
        assert len(differences) == 1
        assert "b" in differences[0]
        assert "unexpected" in differences[0]

    def test_nested_paths_are_dotted(self) -> None:
        differences = diff({"a": {"b": 1}}, {"a": {"b": 2}})
        assert len(differences) == 1
        assert differences[0].startswith("a.b")

    def test_list_indices_are_bracketed(self) -> None:
        differences = diff({"a": [1, 2]}, {"a": [1, 3]})
        assert len(differences) == 1
        assert "a[1]" in differences[0]

    def test_multiple_differences_are_all_reported(self) -> None:
        differences = diff({"a": 1, "b": 2}, {"a": 10, "b": 20})
        assert len(differences) == 2


class TestCompareResults:
    def test_matching_results_report_matches_true_and_no_differences(self) -> None:
        result = compare_results({"length": 10}, {"length": 10})
        assert result == {"matches": True, "differences": []}

    def test_differing_results_report_matches_false_with_differences(self) -> None:
        result = compare_results({"length": 10}, {"length": 11})
        assert result["matches"] is False
        assert len(result["differences"]) == 1

    def test_realistic_nested_verifier_result(self) -> None:
        approved = {
            "table_line_count": {"length": 1400},
            "qrel_stats": {
                "number_of_queries": 225,
                "relevance_counts": {"0": 3, "1": 5},
            },
            "evaluation": {
                "BM25": {"nDCG@10": 0.34331265929286764, "recip_rank": 0.5295741683725248},
            },
        }
        # Same shape, only the evaluation metrics jittered by floating point
        # noise well within tolerance -- should still match overall.
        actual = {
            "table_line_count": {"length": 1400},
            "qrel_stats": {
                "number_of_queries": 225,
                "relevance_counts": {"0": 3, "1": 5},
            },
            "evaluation": {
                "BM25": {"nDCG@10": 0.3433126592928677, "recip_rank": 0.5295741683725249},
            },
        }
        assert compare_results(approved, actual) == {"matches": True, "differences": []}

    def test_realistic_nested_verifier_result_with_a_real_regression(self) -> None:
        approved = {"table_line_count": {"length": 1400}}
        actual = {"table_line_count": {"length": 1350}}
        result = compare_results(approved, actual)
        assert result["matches"] is False
        assert "table_line_count.length" in result["differences"][0]
