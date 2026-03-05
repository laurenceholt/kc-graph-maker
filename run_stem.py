#!/usr/bin/env python3
"""
Single-command orchestrator for the KC extraction pipeline.

Runs the full pipeline for one stem:
  1. Extract question images from PDFs
  2. Extract Knowledge Components via GPT vision API
  3. Auto-deduplicate KCs via GPT
  4. Update stems.json manifest

Usage:
    python run_stem.py "path/to/PDFs" --stem fractions
    python run_stem.py "path/to/PDFs" --stem fractions --resume
    python run_stem.py "path/to/PDFs" --stem fractions --skip-extract
    python run_stem.py "path/to/PDFs" --stem fractions --skip-dedup
"""

import argparse
import json
import os
import subprocess
import sys


def run_step(description, cmd):
    """Run a subprocess step, streaming output. Exit on failure."""
    print(f"\n{'='*60}")
    print(f"STEP: {description}")
    print(f"{'='*60}")
    print(f"  CMD: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
    if result.returncode != 0:
        print(f"\nERROR: Step failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def build_stems_manifest(script_dir):
    """Scan site/data/*/kcs.json to build site/data/stems.json manifest."""
    data_dir = os.path.join(script_dir, "site", "data")
    stems = []

    if not os.path.isdir(data_dir):
        return stems

    for entry in sorted(os.listdir(data_dir)):
        stem_dir = os.path.join(data_dir, entry)
        kcs_path = os.path.join(stem_dir, "kcs.json")
        questions_path = os.path.join(stem_dir, "questions.json")

        if not os.path.isdir(stem_dir) or not os.path.exists(kcs_path):
            continue

        with open(kcs_path) as f:
            kcs = json.load(f)

        q_count = 0
        if os.path.exists(questions_path):
            with open(questions_path) as f:
                q_count = len(json.load(f))

        # Generate a human-readable label from the stem ID
        label = entry.replace('_', ' ').replace('-', ' ').title()

        stems.append({
            "id": entry,
            "label": label,
            "kc_count": len(kcs),
            "question_count": q_count,
        })

    manifest_path = os.path.join(data_dir, "stems.json")
    with open(manifest_path, 'w') as f:
        json.dump(stems, f, indent=2)

    return stems


def main():
    parser = argparse.ArgumentParser(
        description="Run the full KC extraction pipeline for one stem"
    )
    parser.add_argument('pdf_dir',
                        help='Path to folder containing assessment PDFs')
    parser.add_argument('--stem', required=True,
                        help='Stem name (e.g., fractions, multiplication)')
    parser.add_argument('--resume', action='store_true',
                        help='Skip assessments with cached GPT responses')
    parser.add_argument('--skip-extract', action='store_true',
                        help='Skip step 1 (reuse existing question images)')
    parser.add_argument('--skip-kcs', action='store_true',
                        help='Skip step 2 (reuse existing KC extraction)')
    parser.add_argument('--skip-dedup', action='store_true',
                        help='Skip step 3 (no deduplication)')
    parser.add_argument('--model', default='gpt-5.2-chat-latest',
                        help='OpenAI model for KC extraction and dedup')
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_dir = os.path.abspath(args.pdf_dir)
    python = sys.executable  # Use same Python interpreter

    if not os.path.isdir(pdf_dir):
        print(f"ERROR: PDF directory not found: {pdf_dir}")
        sys.exit(1)

    pdf_count = len([f for f in os.listdir(pdf_dir) if f.endswith('.pdf')])
    print(f"KC Extraction Pipeline")
    print(f"  Stem:     {args.stem}")
    print(f"  PDFs:     {pdf_dir} ({pdf_count} files)")
    print(f"  Model:    {args.model}")
    print(f"  Resume:   {args.resume}")

    # Step 1: Extract question images from PDFs
    if not args.skip_extract:
        run_step(
            "Extract question images from PDFs",
            [python, "extract_questions.py", "--export-site",
             "--pdf-dir", pdf_dir, "--stem", args.stem]
        )
    else:
        print(f"\nSkipping question extraction (--skip-extract)")

    # Step 2: Extract KCs via GPT vision API
    if not args.skip_kcs:
        cmd = [python, "extract_kcs.py", "--stem", args.stem, "--model", args.model]
        if args.resume:
            cmd.append("--resume")
        run_step("Extract Knowledge Components via GPT", cmd)
    else:
        print(f"\nSkipping KC extraction (--skip-kcs)")

    # Step 3: Auto-deduplicate KCs
    if not args.skip_dedup:
        run_step(
            "Auto-deduplicate KCs via GPT",
            [python, "dedup_kcs.py", "--stem", args.stem, "--auto",
             "--model", args.model]
        )
    else:
        print(f"\nSkipping deduplication (--skip-dedup)")

    # Step 4: Build stems manifest
    print(f"\n{'='*60}")
    print(f"STEP: Build stems manifest")
    print(f"{'='*60}")

    stems = build_stems_manifest(script_dir)
    print(f"\nStems manifest ({len(stems)} stems):")
    for s in stems:
        print(f"  {s['id']:20s}  {s['kc_count']:4d} KCs  {s['question_count']:4d} questions")

    # Summary
    kcs_path = os.path.join(script_dir, "site", "data", args.stem, "kcs.json")
    questions_path = os.path.join(script_dir, "site", "data", args.stem, "questions.json")

    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE: {args.stem}")
    print(f"{'='*60}")

    if os.path.exists(questions_path):
        with open(questions_path) as f:
            q_count = len(json.load(f))
        print(f"  Questions: {q_count}")

    if os.path.exists(kcs_path):
        with open(kcs_path) as f:
            kc_count = len(json.load(f))
        print(f"  KCs:       {kc_count}")

    print(f"\nDeploy: netlify deploy --prod --dir=site")


if __name__ == "__main__":
    main()
