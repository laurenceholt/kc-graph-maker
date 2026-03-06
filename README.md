# KC Graph Maker

Extracts **Knowledge Components (KCs)** from Eureka Math2 (EM2) PDF assessment solutions using GPT vision, then serves them as a searchable static site on Netlify.

## What It Does

1. **PDF Extraction** - Extracts individual math questions as images from EM2 assessment PDFs
2. **KC Extraction** - Sends question images to GPT-5.2 vision API to identify knowledge components using the KLI (Knowledge-Learning-Instruction) framework
3. **Deduplication** - Merges duplicate KCs within modules and across the full dataset
4. **Static Site** - Serves KCs as a filterable browser at [kc-graph-maker.netlify.app](https://kc-graph-maker.netlify.app)

## Architecture

```
Assessment PDFs
     |
     v
extract_questions.py    # PyMuPDF: PDFs -> question PNG images + questions.json
     |
     v
extract_kcs.py          # OpenAI GPT-5.2 vision: questions -> KCs (kcs.json)
     |
     v
dedup_kcs.py            # GPT-based within-module deduplication
     |
     v
run_module.py           # Orchestrates the above 3 steps for one module
     |
     v
dedup_global.py         # Cross-module deduplication across all modules
     |
     v
site/index.html         # Static site: filters, search, question thumbnails
```

## Directory Structure

```
.
├── extract_questions.py      # PDF -> question images extraction
├── extract_kcs.py            # GPT vision -> KC extraction
├── dedup_kcs.py              # Within-module KC deduplication
├── dedup_global.py           # Cross-module KC deduplication
├── run_module.py             # Single-command pipeline orchestrator
├── site/
│   ├── index.html            # Frontend (single HTML file, no build step)
│   ├── data/
│   │   ├── modules.json      # Module manifest (auto-generated)
│   │   ├── G1_M1/
│   │   │   ├── kcs.json      # Knowledge Components for this module
│   │   │   └── questions.json # Question metadata
│   │   ├── G8_M4/
│   │   │   ├── kcs.json
│   │   │   └── questions.json
│   │   └── ...
│   └── images/
│       ├── G1_M1/            # Question images (PNG)
│       ├── G8_M4/
│       └── ...
├── extracted_kcs/             # Cached GPT responses (not in git)
├── logs/                      # Pipeline logs (not in git)
└── netlify.toml               # Netlify deploy config
```

## Setup

```bash
# Clone
git clone https://github.com/laurenceholt/kc-graph-maker.git
cd kc-graph-maker

# Python environment
python -m venv .venv
source .venv/bin/activate
pip install pymupdf openai python-dotenv pillow numpy

# API key
echo "OPENAI_API_KEY=sk-..." > .env
```

## Usage

### Process a Module

```bash
# Full pipeline: extract questions, extract KCs, deduplicate
python run_module.py "path/to/PDF/folder" --module G8_M4

# With resume (skip already-cached GPT responses)
python run_module.py "path/to/PDF/folder" --module G8_M4 --resume

# Skip steps
python run_module.py "path/to/PDF/folder" --module G8_M4 --skip-extract  # reuse existing images
python run_module.py "path/to/PDF/folder" --module G8_M4 --skip-dedup    # skip dedup step
```

### Cross-Module Deduplication

After processing multiple modules, run global dedup to merge KCs that represent the same skill across different modules:

```bash
# Preview what would be merged
python dedup_global.py --dry-run

# Apply merges
python dedup_global.py
```

### Individual Scripts

```bash
# Extract question images only
python extract_questions.py --pdf-dir "path/to/PDFs" --module G8_M4 --export-site

# Extract KCs only (requires questions.json to exist)
python extract_kcs.py --module G8_M4

# Within-module dedup only
python dedup_kcs.py --module G8_M4 --auto
```

## KC Data Schema

Each KC in `kcs.json` follows the KLI framework:

```json
{
  "kc_id": "pythagorean_theorem_apply",
  "title": "Apply the Pythagorean Theorem",
  "description": "Use a^2 + b^2 = c^2 to find a missing side length...",
  "condition": "A right triangle with two known side lengths",
  "response": "Substitute into a^2 + b^2 = c^2 and solve for the unknown",
  "cond_type": "Variable",
  "resp_type": "Variable",
  "relationship": "Non-verbal",
  "rationale": "No",
  "label": "Principle / Model",
  "example": "Given legs 3 and 4, find hypotenuse: $3^2 + 4^2 = c^2$...",
  "notes": "",
  "question_ids": ["G8_M1_TD_a1_q2", "G8_M2_TD_a1_q1", "G8_M3_a1_q7"]
}
```

## PDF Naming Convention

The extraction pipeline expects PDFs named like:

```
EM2_G{grade}_M{module}[_T{topic}][_L{lesson}][_Assessment]SampleSolutions[Part{n}]_WCAG21[_v{n}].pdf
```

Examples:
- `EM2_G8_M4_TA_SampleSolutions_WCAG21.pdf` (Topic A)
- `EM2_G8_M4_AssessmentSampleSolutions_WCAG21.pdf` (module-level assessment)
- `EM2_G1_M2_TE_L23_SampleSolutions_WCAG21_v2.pdf` (lesson-specific)
- `EM2_G1_M6_TE_SampleSolutionsPart1_WCAG21.pdf` (multi-part)

## Frontend

The site is a single `index.html` file with no build step. It loads all modules' data in parallel and provides:

- **Grade filter** - Filter by grade level
- **Module filter** - Filter by specific module (cascades from grade)
- **Topic filter** - Filter by assessment topic
- **Label filter** - Filter by KC type (Concept, Principle, Skill, etc.)
- **Search** - Full-text search across KC titles, descriptions, and IDs
- **Question thumbnails** - Click to view the original assessment question image

## Deployment

The site is deployed to Netlify via GitHub. Push to `main` triggers auto-deploy.

```bash
# Manual deploy
netlify deploy --prod --dir=site
```

## Key Dependencies

- **PyMuPDF (fitz)** - PDF text extraction and page rendering
- **OpenAI API** - GPT-5.2 vision for KC extraction and dedup analysis
- **Pillow** - Image cropping and stitching
- **NumPy** - Whitespace trimming on extracted images
- **python-dotenv** - API key management

## Cost

GPT API costs per module (~40 questions):
- KC extraction: ~$0.50-1.00 (vision API, ~8 calls)
- Within-module dedup: ~$0.02 (text-only, 1 call)
- Cross-module dedup: ~$0.03 (text-only, 1 call for entire dataset)
