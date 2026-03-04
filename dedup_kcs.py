"""
Deduplicate KCs that were generated independently across assessments.
Merges question_ids and keeps the metadata from the KC with the most questions.
"""
import json

# Each group: canonical_id -> list of duplicate kc_ids to merge INTO it.
# The canonical gets all the question_ids from the duplicates.
# If canonical is not already present, the first existing id becomes canonical.
MERGE_GROUPS = {
    # --- Add fractions (like/common/same denominator) ---
    "add_fractions_common_denominator": [
        "add_fractions_like_denominators",
        "add_fractions_same_denominator",
        "add_like_denominators",
        "add_fractions_same_unit",
    ],

    # --- Subtract fractions (like/common/same denominator) ---
    "subtract_fractions_common_denominator": [
        "subtract_fractions_like_denominators",
        "subtract_fractions_same_denominator",
        "subtract_like_denominators",
    ],

    # --- Subtract mixed numbers ---
    "subtract_mixed_numbers_like_denominators": [
        "subtract_mixed_numbers_with_decomposition",
        "subtract_mixed_numbers_with_regrouping",
        "compute_difference_mixed_numbers",
    ],

    # --- Add mixed numbers (like denominators) ---
    "add_mixed_numbers": [
        "add_mixed_numbers_with_common_denominator",
        "add_mixed_numbers_with_regroup",
        "add_mixed_numbers_no_regroup",
    ],

    # --- Add mixed numbers (unlike denominators) ---
    # Keep add_mixed_numbers_common_denominator separate — it's unlike denoms

    # --- Convert improper fraction to mixed number ---
    "convert_improper_to_mixed": [
        "convert_improper_fraction_to_mixed",
        "express_improper_fraction_as_mixed_number",
    ],

    # --- Whole number as fraction over 1 ---
    "convert_whole_to_fraction_over_one": [
        "whole_number_as_fraction_over_one",
        "complete_fraction_equals_whole_over_one",
        "convert_whole_to_fraction",
    ],

    # --- Denominator as count of equal parts ---
    "count_equal_parts_for_denominator": [
        "count_equal_parts_denominator",
        "count_equal_parts_in_whole",
    ],

    # --- Compare fractions with same numerator ---
    "compare_fractions_common_numerator": [
        "compare_fractions_different_denominators_same_numerator",
        "compare_same_numerator",
    ],

    # --- Compare fractions same-sized wholes ---
    "compare_fractions_same_whole": [
        "compare_fractions_same_whole_requirement",
        "ensure_same_whole_for_comparison",
    ],

    # --- Compare fraction to 1/2 benchmark ---
    "compare_to_one_half": [
        "compare_fractions_using_benchmark_half",
    ],

    # --- Compare sums by estimation ---
    "compare_sum_to_benchmark_by_estimation": [
        "compare_fraction_sums_by_estimation",
    ],

    # --- Use comparison symbols for fractions ---
    "compare_fractions_with_symbols": [
        "compare_fractions_use_symbols",
        "compare_fractions_using_symbols",
        "select_comparison_symbol",
    ],

    # --- Generate equivalent fractions ---
    "generate_equivalent_fraction_by_scaling": [
        "generate_equivalent_fraction_by_multiplying",
        "equivalent_fractions_multiplicative",
        "equivalent_fractions_multiply_one",
        "multiply_to_form_equivalent_fraction",
    ],

    # --- Find common denominator ---
    "find_common_denominator": [
        "find_common_denominator_lcm",
        "identify_common_denominator",
        "convert_to_common_denominator",
    ],

    # --- Fraction as multiple of unit fraction ---
    "fraction_as_multiple_of_unit_fraction": [
        "fraction_as_numerator_of_unit_fraction",
    ],

    # --- Interpret division as fraction / fraction as division ---
    "interpret_fraction_as_division": [
        "divide_whole_by_whole_as_fraction",
        "convert_division_to_fraction",
        "construct_division_equation_from_fraction",
    ],

    # --- Division as equal sharing ---
    "model_equal_sharing_division": [
        "interpret_division_context_equal_shares",
        "represent_equal_sharing_as_division",
    ],

    # --- Division as measurement / number of groups ---
    "interpret_division_context_measurement": [
        "interpret_fraction_division_context",
    ],

    # --- Interpret fraction from tape/parts model ---
    "interpret_tape_diagram_fraction": [
        "interpret_fraction_from_tape_diagram",
    ],

    # --- Multiply fraction by whole number ---
    "multiply_fraction_by_whole": [
        "multiply_fraction_by_whole_number",
        "multiply_whole_by_fraction",
    ],

    # --- Multiply fractions ---
    "multiply_fractions": [
        "multiply_fraction_by_fraction",
    ],

    # --- Divide by fraction using reciprocal ---
    "divide_by_fraction_multiply_reciprocal": [
        "divide_by_fraction",
        "relate_division_and_multiplication",
        "relate_division_to_multiplication_reciprocal",
    ],

    # --- Plot/locate fraction on number line ---
    "plot_fraction_on_number_line": [
        "plot_fraction_number_line",
        "locate_fraction_on_number_line",
    ],

    # --- Identify/determine fraction from number line ---
    "determine_fraction_from_number_line": [
        "determine_fraction_from_point",
    ],

    # --- Partition into equal parts ---
    "partition_whole_into_equal_parts": [
        "partition_shape_into_equal_parts",
        "partition_number_line_equal_parts",
        "partition_unit_interval_equal_parts",
        "partition_unit_interval_into_equal_parts",
        "partition_whole_into_equal_denominator_parts",
    ],

    # --- Complete equivalent fraction ---
    "complete_missing_equivalent_fraction": [
        "complete_equivalent_fraction_missing_denominator",
        "complete_equivalent_fraction_missing_numerator",
        "complete_equivalent_fraction_equation",
    ],

    # --- Identify equivalent fractions on number line ---
    "identify_equivalent_fractions_number_line": [
        "identify_equivalent_fraction_on_number_line",
        "equivalent_fractions_same_point",
    ],

    # --- Recognize equivalent fractions ---
    "recognize_equivalent_fractions": [
        "match_equivalent_fractions",
    ],

    # --- Decompose fraction ---
    "decompose_fraction_sum": [
        "decompose_fraction_same_denominator",
        "decompose_fraction_sum_of_unit_fractions",
    ],

    # --- Translate word/verbal to expression ---
    "translate_word_phrase_to_expression": [
        "translate_words_to_expression_operations",
        "translate_word_problem_to_expression",
    ],

    # --- Shade parts to represent fraction ---
    "shade_numerator_parts": [
        "shade_specified_number_of_parts",
        "represent_fraction_by_shading",
    ],

    # --- Identify fraction from shaded model ---
    "identify_shaded_fraction_from_equal_parts": [
        "interpret_shaded_fraction_model",
        "identify_equal_parts_in_model",
    ],

    # --- Multiplying by fraction < 1 decreases value ---
    "multiply_by_fraction_less_than_one_effect": [
        "fraction_less_than_one_scales_down",
    ],

    # --- Compare fractions with common/same denominator ---
    "compare_fractions_common_denominator": [
        "compare_same_denominator",
    ],

    # --- Multiply whole by mixed number ---
    # Already merged by extract_kcs, no action needed

    # --- Compare fractions using number line ---
    "compare_fractions_number_line": [
        "use_number_line_to_compare_fractions",
        "interpret_number_line_position",
    ],
}


def main():
    with open("site/data/kcs.json") as f:
        kcs = json.load(f)

    kc_by_id = {k["kc_id"]: k for k in kcs}

    # Build reverse map: any id -> canonical id
    id_to_canonical = {}
    for canonical, dupes in MERGE_GROUPS.items():
        for d in dupes:
            id_to_canonical[d] = canonical

    merged_ids = set()
    merge_count = 0

    for canonical, dupes in MERGE_GROUPS.items():
        # Collect all KCs in this group that exist
        group_ids = [canonical] + dupes
        group_kcs = [kc_by_id[gid] for gid in group_ids if gid in kc_by_id]

        if len(group_kcs) <= 1:
            continue  # nothing to merge

        # Pick the one with the most questions as the base
        group_kcs.sort(key=lambda k: len(k["question_ids"]), reverse=True)
        base = group_kcs[0]

        # Collect all question_ids from duplicates
        all_qids = set()
        for k in group_kcs:
            all_qids.update(k["question_ids"])

        base["question_ids"] = sorted(all_qids)

        # Mark duplicates (non-base) for removal
        for k in group_kcs[1:]:
            merged_ids.add(k["kc_id"])
            merge_count += 1

        # If the base id isn't the canonical, update it
        if base["kc_id"] != canonical and canonical in kc_by_id:
            # canonical exists but isn't the base — that's fine, base has more questions
            pass

    # Remove merged duplicates
    deduped = [k for k in kcs if k["kc_id"] not in merged_ids]
    deduped.sort(key=lambda k: k["title"].lower())

    print(f"Before: {len(kcs)} KCs")
    print(f"Merged: {merge_count} duplicates into their canonical KCs")
    print(f"After:  {len(deduped)} KCs")

    # Show merge results
    print(f"\nMerge groups applied:")
    for canonical, dupes in sorted(MERGE_GROUPS.items()):
        group_ids = [canonical] + dupes
        existing = [gid for gid in group_ids if gid in kc_by_id]
        if len(existing) > 1:
            # Find which one survived
            survivor = [k for k in deduped if k["kc_id"] in existing]
            if survivor:
                s = survivor[0]
                removed = [gid for gid in existing if gid != s["kc_id"]]
                print(f"  {s['kc_id']:50s} ← absorbed {removed}")
                print(f"    Now has {len(s['question_ids'])} questions")

    with open("site/data/kcs.json", "w") as f:
        json.dump(deduped, f, indent=2)

    print(f"\nWrote {len(deduped)} KCs to site/data/kcs.json")


if __name__ == "__main__":
    main()
