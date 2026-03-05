#!/usr/bin/env python3
"""
Deduplicate KCs that were generated independently across assessments.
Merges question_ids and keeps the metadata from the KC with the most questions.

Supports two modes:
  --auto    GPT-based automatic duplicate detection (for new modules)
  (default) Legacy hardcoded merge groups (for Fractions, backward compat)

Usage:
    # Auto-dedup for a module
    python dedup_kcs.py --module G3_M5 --auto

    # Legacy mode (hardcoded Fractions merge groups)
    python dedup_kcs.py

    # Dry run — show detected groups without applying
    python dedup_kcs.py --module G3_M5 --auto --dry-run
"""

import argparse
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# --- Legacy hardcoded merge groups (Fractions only) ---
LEGACY_MERGE_GROUPS = {
    "add_fractions_common_denominator": [
        "add_fractions_like_denominators", "add_fractions_same_denominator",
        "add_like_denominators", "add_fractions_same_unit",
    ],
    "subtract_fractions_common_denominator": [
        "subtract_fractions_like_denominators", "subtract_fractions_same_denominator",
        "subtract_like_denominators",
    ],
    "subtract_mixed_numbers_like_denominators": [
        "subtract_mixed_numbers_with_decomposition", "subtract_mixed_numbers_with_regrouping",
        "compute_difference_mixed_numbers",
    ],
    "add_mixed_numbers": [
        "add_mixed_numbers_with_common_denominator", "add_mixed_numbers_with_regroup",
        "add_mixed_numbers_no_regroup",
    ],
    "convert_improper_to_mixed": [
        "convert_improper_fraction_to_mixed", "express_improper_fraction_as_mixed_number",
    ],
    "convert_whole_to_fraction_over_one": [
        "whole_number_as_fraction_over_one", "complete_fraction_equals_whole_over_one",
        "convert_whole_to_fraction",
    ],
    "count_equal_parts_for_denominator": [
        "count_equal_parts_denominator", "count_equal_parts_in_whole",
    ],
    "compare_fractions_common_numerator": [
        "compare_fractions_different_denominators_same_numerator", "compare_same_numerator",
    ],
    "compare_fractions_same_whole": [
        "compare_fractions_same_whole_requirement", "ensure_same_whole_for_comparison",
    ],
    "compare_to_one_half": ["compare_fractions_using_benchmark_half"],
    "compare_sum_to_benchmark_by_estimation": ["compare_fraction_sums_by_estimation"],
    "compare_fractions_with_symbols": [
        "compare_fractions_use_symbols", "compare_fractions_using_symbols",
        "select_comparison_symbol",
    ],
    "generate_equivalent_fraction_by_scaling": [
        "generate_equivalent_fraction_by_multiplying", "equivalent_fractions_multiplicative",
        "equivalent_fractions_multiply_one", "multiply_to_form_equivalent_fraction",
    ],
    "find_common_denominator": [
        "find_common_denominator_lcm", "identify_common_denominator",
        "convert_to_common_denominator",
    ],
    "fraction_as_multiple_of_unit_fraction": ["fraction_as_numerator_of_unit_fraction"],
    "interpret_fraction_as_division": [
        "divide_whole_by_whole_as_fraction", "convert_division_to_fraction",
        "construct_division_equation_from_fraction",
    ],
    "model_equal_sharing_division": [
        "interpret_division_context_equal_shares", "represent_equal_sharing_as_division",
    ],
    "interpret_division_context_measurement": ["interpret_fraction_division_context"],
    "interpret_tape_diagram_fraction": ["interpret_fraction_from_tape_diagram"],
    "multiply_fraction_by_whole": [
        "multiply_fraction_by_whole_number", "multiply_whole_by_fraction",
    ],
    "multiply_fractions": ["multiply_fraction_by_fraction"],
    "divide_by_fraction_multiply_reciprocal": [
        "divide_by_fraction", "relate_division_and_multiplication",
        "relate_division_to_multiplication_reciprocal",
    ],
    "plot_fraction_on_number_line": [
        "plot_fraction_number_line", "locate_fraction_on_number_line",
    ],
    "determine_fraction_from_number_line": ["determine_fraction_from_point"],
    "partition_whole_into_equal_parts": [
        "partition_shape_into_equal_parts", "partition_number_line_equal_parts",
        "partition_unit_interval_equal_parts", "partition_unit_interval_into_equal_parts",
        "partition_whole_into_equal_denominator_parts",
    ],
    "complete_missing_equivalent_fraction": [
        "complete_equivalent_fraction_missing_denominator",
        "complete_equivalent_fraction_missing_numerator",
        "complete_equivalent_fraction_equation",
    ],
    "identify_equivalent_fractions_number_line": [
        "identify_equivalent_fraction_on_number_line", "equivalent_fractions_same_point",
    ],
    "recognize_equivalent_fractions": ["match_equivalent_fractions"],
    "decompose_fraction_sum": [
        "decompose_fraction_same_denominator", "decompose_fraction_sum_of_unit_fractions",
    ],
    "translate_word_phrase_to_expression": [
        "translate_words_to_expression_operations", "translate_word_problem_to_expression",
    ],
    "shade_numerator_parts": [
        "shade_specified_number_of_parts", "represent_fraction_by_shading",
    ],
    "identify_shaded_fraction_from_equal_parts": [
        "interpret_shaded_fraction_model", "identify_equal_parts_in_model",
    ],
    "multiply_by_fraction_less_than_one_effect": ["fraction_less_than_one_scales_down"],
    "compare_fractions_common_denominator": ["compare_same_denominator"],
    "compare_fractions_number_line": [
        "use_number_line_to_compare_fractions", "interpret_number_line_position",
    ],
}


# --- GPT auto-dedup prompt ---
AUTO_DEDUP_PROMPT = """You are a deduplication specialist for Knowledge Components (KCs) extracted from math assessments.

Below is a list of KC IDs and their titles. Many KCs describe the same underlying skill but were generated independently from different assessments, so they have slightly different names.

Your task: identify groups of duplicate KCs that should be merged. Two KCs are duplicates if they represent the same underlying mathematical skill or concept, even if named differently.

RULES:
- Each group must have a "canonical" ID (the best/most descriptive name) and a list of "duplicates" to merge into it.
- A KC can appear in at most ONE group (either as canonical or as a duplicate).
- Only group KCs that are genuinely the same skill. Do NOT group KCs that are merely related.
- If a KC has no duplicates, do NOT include it.
- The canonical ID should be the clearest, most descriptive name from the group.

Return a JSON object with a single key "merge_groups" containing an object where:
- Each key is the canonical kc_id
- Each value is an array of duplicate kc_ids to merge into it

Example:
{"merge_groups": {"add_fractions_common_denominator": ["add_fractions_like_denominators", "add_fractions_same_denominator"]}}

Here are the KCs to analyze:

"""


def auto_detect_merge_groups(kcs, client, model="gpt-5.2-chat-latest"):
    """Use GPT to detect duplicate KC groups automatically."""
    # Build the KC list for the prompt
    kc_list = "\n".join(f"- {k['kc_id']}: {k['title']}" for k in kcs)
    prompt = AUTO_DEDUP_PROMPT + kc_list

    print(f"  Sending {len(kcs)} KCs to GPT for dedup analysis...")

    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )

    raw_text = response.choices[0].message.content
    usage = response.usage
    print(f"  Tokens: {usage.prompt_tokens} in, {usage.completion_tokens} out")

    # Parse response
    import re
    text = raw_text.strip()
    if text.startswith("```"):
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    data = json.loads(text)
    groups = data.get("merge_groups", {})

    # Validate: every ID must exist in our KC set
    kc_ids = {k["kc_id"] for k in kcs}
    seen = set()
    valid_groups = {}

    for canonical, dupes in groups.items():
        if canonical not in kc_ids:
            print(f"  WARNING: canonical '{canonical}' not found in KCs, skipping group")
            continue

        valid_dupes = []
        for d in dupes:
            if d not in kc_ids:
                print(f"  WARNING: duplicate '{d}' not found in KCs, skipping")
                continue
            if d in seen:
                print(f"  WARNING: '{d}' already in another group, skipping")
                continue
            valid_dupes.append(d)
            seen.add(d)

        if valid_dupes:
            if canonical in seen:
                print(f"  WARNING: canonical '{canonical}' already in another group, skipping")
                continue
            seen.add(canonical)
            valid_groups[canonical] = valid_dupes

    return valid_groups


def apply_merge_groups(kcs, merge_groups):
    """Apply merge groups to a list of KCs. Returns (deduped_kcs, merge_count)."""
    kc_by_id = {k["kc_id"]: k for k in kcs}

    merged_ids = set()
    merge_count = 0

    for canonical, dupes in merge_groups.items():
        group_ids = [canonical] + dupes
        group_kcs = [kc_by_id[gid] for gid in group_ids if gid in kc_by_id]

        if len(group_kcs) <= 1:
            continue

        # Pick the one with the most questions as the base
        group_kcs.sort(key=lambda k: len(k["question_ids"]), reverse=True)
        base = group_kcs[0]

        # Collect all question_ids
        all_qids = set()
        for k in group_kcs:
            all_qids.update(k["question_ids"])
        base["question_ids"] = sorted(all_qids)

        # Mark duplicates for removal
        for k in group_kcs[1:]:
            merged_ids.add(k["kc_id"])
            merge_count += 1

    deduped = [k for k in kcs if k["kc_id"] not in merged_ids]
    deduped.sort(key=lambda k: k["title"].lower())

    return deduped, merge_count


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate KCs across assessments"
    )
    parser.add_argument('--module',
                        help='Module ID (e.g., G3_M5). Uses module-scoped paths.')
    parser.add_argument('--auto', action='store_true',
                        help='Use GPT to auto-detect duplicate groups')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show detected groups without applying')
    parser.add_argument('--model', default='gpt-5.2-chat-latest',
                        help='OpenAI model for auto-dedup')
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Resolve paths
    if args.module:
        kcs_path = os.path.join(script_dir, "site", "data", args.module, "kcs.json")
        cache_dir = os.path.join(script_dir, "extracted_kcs", args.module)
    else:
        kcs_path = os.path.join(script_dir, "site", "data", "kcs.json")
        cache_dir = os.path.join(script_dir, "extracted_kcs")

    if not os.path.exists(kcs_path):
        print(f"ERROR: KCs file not found: {kcs_path}")
        sys.exit(1)

    with open(kcs_path) as f:
        kcs = json.load(f)

    print(f"Loaded {len(kcs)} KCs from {os.path.relpath(kcs_path, script_dir)}")

    # Determine merge groups
    if args.auto:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("ERROR: OPENAI_API_KEY not set. Add it to .env")
            sys.exit(1)
        client = OpenAI(api_key=api_key)

        merge_groups = auto_detect_merge_groups(kcs, client, args.model)

        # Cache detected groups for auditability
        os.makedirs(cache_dir, exist_ok=True)
        groups_path = os.path.join(cache_dir, "merge_groups.json")
        with open(groups_path, 'w') as f:
            json.dump(merge_groups, f, indent=2)
        print(f"  Cached merge groups to {os.path.relpath(groups_path, script_dir)}")
    else:
        merge_groups = LEGACY_MERGE_GROUPS

    # Show groups
    kc_by_id = {k["kc_id"]: k for k in kcs}
    active_groups = {c: d for c, d in merge_groups.items()
                     if sum(1 for gid in [c] + d if gid in kc_by_id) > 1}

    print(f"\nFound {len(active_groups)} merge groups with active duplicates:")
    for canonical, dupes in sorted(active_groups.items()):
        existing = [gid for gid in [canonical] + dupes if gid in kc_by_id]
        print(f"  {canonical} <- {[d for d in existing if d != canonical]}")

    if args.dry_run:
        print("\nDry run — no changes applied.")
        return

    # Apply merges
    deduped, merge_count = apply_merge_groups(kcs, merge_groups)

    print(f"\nBefore: {len(kcs)} KCs")
    print(f"Merged: {merge_count} duplicates")
    print(f"After:  {len(deduped)} KCs")

    with open(kcs_path, 'w') as f:
        json.dump(deduped, f, indent=2)

    print(f"Wrote {len(deduped)} KCs to {os.path.relpath(kcs_path, script_dir)}")


if __name__ == "__main__":
    main()
