#!/usr/bin/env python3
"""
Cross-module KC deduplication.

Detects and merges Knowledge Components that represent the same skill
but appear in different modules' kcs.json files.

Usage:
    python dedup_global.py              # Auto-detect and merge cross-module duplicates
    python dedup_global.py --dry-run    # Show what would be merged without writing
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()


# --- GPT prompt for cross-module dedup ---
GLOBAL_DEDUP_PROMPT = """You are a deduplication specialist for Knowledge Components (KCs) extracted from math assessments across multiple curriculum modules.

Below is a list of KC IDs with their titles. The module in brackets is for context only. The same mathematical skill may appear in multiple modules with the same or different kc_ids.

Your task: identify groups of duplicate KCs that should be merged into a single KC. Two KCs are duplicates if they represent the same underlying mathematical skill or concept, even if:
- They have different kc_ids but describe the same skill
- They appear in different grade/module contexts but test the same competency
- They have slightly different names or phrasings

RULES:
- Each group must have a "canonical" kc_id and a list of "duplicate" kc_ids to merge into it.
- Use ONLY the kc_id (e.g. "pythagorean_theorem_apply"), NOT the module prefix. Do NOT include module names in the IDs.
- A kc_id can appear in at most ONE group (either as canonical or as a duplicate).
- Only group KCs that are genuinely the same skill. Do NOT group KCs that are merely related.
- If a kc_id appears in multiple modules but is already the same ID, still include it as a group (canonical = that ID, duplicates = empty list is fine, but preferably just skip it since there's nothing to rename).
- The canonical ID should be the clearest, most descriptive name from the group.

Return a JSON object with a single key "merge_groups" containing an object where:
- Each key is the canonical kc_id (just the ID, no module prefix)
- Each value is an array of duplicate kc_ids to merge into it (just the IDs, no module prefix)

Example:
{"merge_groups": {"pythagorean_theorem_apply": ["apply_pythagorean_theorem", "pythagorean_theorem_application"]}}

Here are the KCs to analyze:

"""


def load_all_module_kcs(script_dir):
    """Load KCs from all modules, tagging each with its source module."""
    data_dir = os.path.join(script_dir, "site", "data")
    module_kcs = {}

    for entry in sorted(os.listdir(data_dir)):
        kcs_path = os.path.join(data_dir, entry, "kcs.json")
        if not os.path.isdir(os.path.join(data_dir, entry)):
            continue
        if not os.path.exists(kcs_path):
            continue

        with open(kcs_path) as f:
            kcs = json.load(f)

        for kc in kcs:
            kc["_module"] = entry

        module_kcs[entry] = kcs

    return module_kcs


def auto_detect_global_merge_groups(module_kcs, client, model="gpt-5.2-chat-latest"):
    """Use GPT to detect cross-module duplicate KC groups."""
    # Build KC list with module context
    lines = []
    all_kc_ids = set()

    for mod_id, kcs in sorted(module_kcs.items()):
        for kc in kcs:
            lines.append(f"- [{mod_id}] {kc['kc_id']}: {kc['title']}")
            all_kc_ids.add(kc["kc_id"])

    kc_list = "\n".join(lines)
    prompt = GLOBAL_DEDUP_PROMPT + kc_list

    total_kcs = sum(len(kcs) for kcs in module_kcs.values())
    print(f"  Sending {total_kcs} KCs ({len(all_kc_ids)} distinct IDs) to GPT...")

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
    text = raw_text.strip()
    if text.startswith("```"):
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    data = json.loads(text)
    raw_groups = data.get("merge_groups", {})

    # Strip any module prefixes GPT may have added (e.g. "G8_M2.kc_id" -> "kc_id")
    def strip_prefix(kc_id):
        if "." in kc_id:
            parts = kc_id.split(".", 1)
            if re.match(r'G\d+_M\d+', parts[0]):
                return parts[1]
        return kc_id

    groups = {}
    for canonical, dupes in raw_groups.items():
        clean_canonical = strip_prefix(canonical)
        clean_dupes = [strip_prefix(d) for d in dupes]
        # Deduplicate in case stripping prefixes creates duplicates
        seen_dupes = set()
        unique_dupes = []
        for d in clean_dupes:
            if d != clean_canonical and d not in seen_dupes:
                unique_dupes.append(d)
                seen_dupes.add(d)
        if unique_dupes:
            groups[clean_canonical] = unique_dupes

    # Validate: every ID must exist in our KC corpus
    seen = set()
    valid_groups = {}

    for canonical, dupes in groups.items():
        if canonical not in all_kc_ids:
            print(f"  WARNING: canonical '{canonical}' not found, skipping group")
            continue

        valid_dupes = []
        for d in dupes:
            if d not in all_kc_ids:
                print(f"  WARNING: duplicate '{d}' not found, skipping")
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


def detect_same_id_duplicates(module_kcs):
    """Find kc_ids that appear in multiple modules (exact ID match)."""
    from collections import Counter
    kc_module_count = defaultdict(list)
    for mod_id, kcs in module_kcs.items():
        for kc in kcs:
            kc_module_count[kc["kc_id"]].append(mod_id)

    # Return kc_ids that exist in 2+ modules
    return {kid: mods for kid, mods in kc_module_count.items() if len(mods) > 1}


def apply_global_merge_groups(module_kcs, merge_groups):
    """
    Apply cross-module merge groups.

    For each merge group:
    1. Find all instances of the canonical and duplicate kc_ids across all modules
    2. Collect all question_ids from all instances
    3. Pick the instance with the most question_ids as the base
    4. Keep the base in its home module with all merged question_ids
    5. Remove all other instances from their respective modules

    Returns: (updated module_kcs dict, list of merge reports)
    """
    # Build lookup: kc_id -> [(module_id, kc_dict), ...]
    kc_index = defaultdict(list)
    for mod_id, kcs in module_kcs.items():
        for kc in kcs:
            kc_index[kc["kc_id"]].append((mod_id, kc))

    # Track which (module, kc object) pairs to remove
    remove_set = set()  # set of python id() values for kc dicts to remove
    reports = []

    for canonical_id, dupe_ids in merge_groups.items():
        group_ids = list(dict.fromkeys([canonical_id] + dupe_ids))  # dedupe, preserve order

        # Gather all (module, kc) instances for every ID in this group
        all_instances = []
        for gid in group_ids:
            for mod_id, kc in kc_index.get(gid, []):
                all_instances.append((mod_id, kc))

        if len(all_instances) <= 1:
            continue

        # Collect all question_ids
        all_qids = set()
        for _, kc in all_instances:
            all_qids.update(kc["question_ids"])

        # Pick the instance with the most questions as the base
        all_instances.sort(key=lambda x: len(x[1]["question_ids"]), reverse=True)
        home_module, base_kc = all_instances[0]

        # Update the base: use canonical_id and merge all question_ids
        base_kc["kc_id"] = canonical_id
        base_kc["question_ids"] = sorted(all_qids)

        # Mark all other instances for removal
        removed_from = []
        for mod_id, kc in all_instances[1:]:
            remove_set.add(id(kc))
            removed_from.append(f"{mod_id}/{kc['kc_id']}")

        reports.append({
            "canonical": canonical_id,
            "home_module": home_module,
            "question_count": len(all_qids),
            "removed": removed_from,
        })

    # Remove merged entries from each module's KC list
    for mod_id in module_kcs:
        module_kcs[mod_id] = [
            kc for kc in module_kcs[mod_id]
            if id(kc) not in remove_set
        ]
        # Sort alphabetically by title
        module_kcs[mod_id].sort(key=lambda k: k["title"].lower())

    return module_kcs, reports


def write_module_kcs(module_kcs, script_dir):
    """Write updated kcs.json for each module, stripping internal tags."""
    data_dir = os.path.join(script_dir, "site", "data")

    for mod_id, kcs in sorted(module_kcs.items()):
        # Strip internal tags before writing
        for kc in kcs:
            kc.pop("_module", None)

        kcs_path = os.path.join(data_dir, mod_id, "kcs.json")
        with open(kcs_path, 'w') as f:
            json.dump(kcs, f, indent=2)
        print(f"  {mod_id}: {len(kcs)} KCs")


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate KCs across all modules"
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Show detected groups without applying')
    parser.add_argument('--model', default='gpt-5.2-chat-latest',
                        help='OpenAI model for dedup analysis')
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Step 1: Load all modules
    module_kcs = load_all_module_kcs(script_dir)
    total_kcs = sum(len(kcs) for kcs in module_kcs.values())
    print(f"Loaded {total_kcs} KCs across {len(module_kcs)} modules")
    for mod_id, kcs in sorted(module_kcs.items()):
        print(f"  {mod_id}: {len(kcs)} KCs")

    # Step 2: Detect cross-module duplicates via GPT
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set. Add it to .env")
        sys.exit(1)
    client = OpenAI(api_key=api_key)

    # Step 2a: Detect same-ID cross-module duplicates (no GPT needed)
    same_id_dupes = detect_same_id_duplicates(module_kcs)
    if same_id_dupes:
        print(f"\n{len(same_id_dupes)} kc_ids appear in multiple modules (auto-merge):")
        for kid, mods in sorted(same_id_dupes.items()):
            print(f"  {kid}: {mods}")

    # Step 2b: Detect different-ID cross-module duplicates via GPT
    gpt_merge_groups = auto_detect_global_merge_groups(module_kcs, client, args.model)

    # Cache GPT merge groups for auditability
    cache_dir = os.path.join(script_dir, "extracted_kcs")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, "global_merge_groups.json")
    with open(cache_path, 'w') as f:
        json.dump(gpt_merge_groups, f, indent=2)
    print(f"\nCached GPT merge groups to extracted_kcs/global_merge_groups.json")

    # Combine: GPT groups handle ID renames; same-ID dupes are handled
    # automatically by apply_global_merge_groups (it finds all instances
    # of each kc_id across modules). We just need to ensure same-ID dupes
    # are included as merge groups too (canonical = the ID, dupes = empty).
    merge_groups = dict(gpt_merge_groups)
    for kid in same_id_dupes:
        if kid not in merge_groups and not any(kid in dupes for dupes in merge_groups.values()):
            merge_groups[kid] = []  # no renames, just consolidate across modules

    # Step 3: Show merge plan
    has_renames = {k: v for k, v in merge_groups.items() if v}
    has_same_id = {k: v for k, v in merge_groups.items() if not v}

    if not merge_groups:
        print("\nNo cross-module duplicates found.")
        return

    if has_renames:
        print(f"\n{len(has_renames)} cross-module rename groups (different IDs, same skill):")
        for canonical, dupes in sorted(has_renames.items()):
            print(f"  {canonical} <- {dupes}")
    if has_same_id:
        print(f"\n{len(has_same_id)} same-ID cross-module consolidations:")
        for kid in sorted(has_same_id):
            print(f"  {kid} ({', '.join(same_id_dupes[kid])})")

    if args.dry_run:
        print("\nDry run — no changes applied.")
        return

    # Step 4: Apply merges
    module_kcs, reports = apply_global_merge_groups(module_kcs, merge_groups)

    # Step 5: Print report
    new_total = sum(len(kcs) for kcs in module_kcs.values())
    total_removed = sum(len(r["removed"]) for r in reports)

    print(f"\nMerge report ({len(reports)} groups applied):")
    for r in reports:
        print(f"\n  {r['canonical']} (kept in {r['home_module']}, {r['question_count']} questions)")
        for removed in r["removed"]:
            print(f"    removed: {removed}")

    print(f"\nBefore: {total_kcs} KC entries")
    print(f"Removed: {total_removed} duplicates")
    print(f"After:  {new_total} KC entries")

    # Step 6: Write back
    print(f"\nWriting updated kcs.json files:")
    write_module_kcs(module_kcs, script_dir)

    # Step 7: Rebuild modules manifest
    sys.path.insert(0, script_dir)
    from run_module import build_modules_manifest
    modules = build_modules_manifest(script_dir)

    print(f"\nUpdated modules.json ({len(modules)} modules):")
    for m in modules:
        print(f"  {m['id']:10s}  {m['kc_count']:4d} KCs  {m['question_count']:4d} questions")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
