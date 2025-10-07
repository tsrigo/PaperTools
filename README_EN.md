# PaperTools

English | [中文](README.md)

PaperTools is a complete academic paper processing pipeline that provides automated paper crawling, intelligent filtering, summary generation, and web page generation.

## Features

- **Automated Crawling**: Automatically crawl the latest papers from academic platforms like arXiv.
- **LLM-Powered Filtering**: Use Large Language Models to intelligently filter papers based on research areas.
- **Automatic Summarization**: Generate high-quality Chinese summaries by fetching full paper content via jina.ai.
- **Inspiration Tracing**: Deeply analyze the evolution of a paper's innovative ideas, from challenge identification to the complete logical chain of the solution.
- **Web Page Generation**: Convert papers into modern, interactive HTML pages with support for collapsible content.
- **Local Deployment**: One-click startup of a local server for easy browsing and sharing.
- **Interactive Features**: Supports paper bookmarking, read status tracking, and deletion with persistent state saving.

## System Requirements

- Python 3.7+
- Internet connection (for API calls and content retrieval)
- Recommended: 4GB+ RAM (when processing a large number of papers)

## Installation and Usage

### Environment Setup

```bash
# 1. Copy the configuration template
cp .env.example .env

# 2. Edit the .env file and set your API key
# OPENAI_API_KEY=your_actual_api_key_here
# OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# MODEL=glm-4.5-flash

# 3. Check and install dependencies
python papertools.py check
```

### Quick Start

```bash
python papertools.py run --mode quick
# Get help
python papertools.py --help
```

## Usage

### Main Commands

```bash
# Run the paper processing pipeline
python papertools.py run [options]
  --mode {quick,full}     # Processing mode: quick(10 papers) or full(1000 papers, default)
  --date YYYY-MM-DD       # Process papers from a specific date
  --categories cs.AI cs.CL # Specify paper categories
  --max-papers-total N    # Custom number of papers

# Start the web server
python papertools.py serve

# Clean cache files
python papertools.py clean

# Check environment and dependencies
python papertools.py check
```

### Advanced Usage: Individual Modules

To use a module individually:

```bash
# 1. Crawl papers
python src/core/crawl_arxiv.py --categories cs.AI cs.CV --max-papers 100

# 2. Filter papers
python src/core/select_.py --input-file arxiv_paper/papers.json

# 3. Generate summaries and inspiration traces
python src/core/generate_summary.py --input-file domain_paper/filtered_papers.json

# 4. Generate the unified web page
python src/core/generate_unified_index.py

# 5. Start the server
python src/core/serve_webpages.py --port 8080
```

## 🚀 Deploy to GitHub Pages

You can publish the generated paper website for free on GitHub Pages for public access and sharing. The recommended method is to use Fork + GitHub Actions for fully automated deployment.

### Step 1: Fork This Repository
Click the **Fork** button in the upper-right corner of this page to copy this project to your own GitHub account.

### Step 2: Configure Pages and Actions Permissions

1.  **Configure Pages Source**:
    *   In your forked repository's page, go to `Settings` > `Pages`.
    *   Under `Build and deployment`, in the `Source` option, select `GitHub Actions`.

2.  **Configure Actions Permissions (Crucial Step)**:
    *   On the repository page, go to `Settings` > `Actions` > `General`.
    *   Scroll down to the `Workflow permissions` section.
    *   Select `Read and write permissions`.
    *   Check the box for `Allow GitHub Actions to create and approve pull requests`.
    *   Click `Save`.

    *This setting grants the Action the necessary permissions to push the built website files to the `gh-pages` branch.*

### Step 3: Trigger Automatic Deployment and Access
- **First Deployment**: After completing the configuration above, the Action will run automatically once (or you can manually trigger `Deploy to GitHub Pages` in the `Actions` tab). Wait a few minutes.
- **Updating the Website**: If you want to customize the filtering rules, you can modify the `PAPER_FILTER_PROMPT` in `src/utils/config.py` and then push the changes to your repository's `main` branch. GitHub Actions will automatically regenerate and deploy the website.

After successful deployment, your website will be available at `https://<your-username>.github.io/<repository-name>/`.

### Alternative: Manual Deployment
If you don't want to use Actions, you can also generate the website locally and then manually upload the contents of the `webpages` directory to any static website hosting service.

## Configuration
The project's core configuration is centralized in two files: `.env` for sensitive information and environment-specific variables, and `src/utils/config.py` for defining the program's default behaviors and parameters.

### Environment Variables (`.env`)

Create a `.env` file in the project root (you can copy it from `.env.example`) to configure the following:

```bash
# API Configuration (Required)
OPENAI_API_KEY=your_api_key_here         # Your large model API key
OPENAI_BASE_URL=https://api.example.com/v1 # API endpoint URL
MODEL=your_model_name                    # Name of the model to use

# Jina API Configuration (Optional, for full-text reading)
JINA_API_TOKEN=your_jina_token_here      # Token for the Jina Reader API
```

### Core Configuration File (`src/utils/config.py`)

This file defines the default behaviors of the pipeline. You can customize it to fit your needs.

#### Key Configuration Parameters

-   **API & Request Related**
    -   `TEMPERATURE`: The temperature for model content generation; lower values produce more stable results.
    -   `REQUEST_TIMEOUT`: API request timeout in seconds.
    -   `REQUEST_DELAY`: Delay between two requests in seconds, to avoid rate limiting.

-   **Directory Configuration**
    -   `ARXIV_PAPER_DIR`, `DOMAIN_PAPER_DIR`, `SUMMARY_DIR`, `WEBPAGES_DIR`: Define the storage directories for the output files of each pipeline stage.

-   **Cache Configuration**
    -   `ENABLE_CACHE`: Whether to enable caching. It is recommended to keep this `True` to save time and API call costs.
    -   `CACHE_EXPIRY_DAYS`: The number of days a cache entry is valid.

-   **Crawling & Processing Limits**
    -   `CRAWL_CATEGORIES`: Default arXiv categories to crawl.
    -   `MAX_PAPERS_PER_CATEGORY`: Maximum number of papers to crawl per category.
    -   `MAX_PAPERS_TOTAL_QUICK`: Total number of papers to process in `quick` mode.
    -   `MAX_PAPERS_TOTAL_FULL`: Total number of papers to process in `full` mode.
    -   `MAX_PAPERS_TOTAL_DEFAULT`: Default number of papers to process when running `pipeline.py` directly.

-   **Concurrency Control**
    -   `MAX_WORKERS`: Global maximum number of concurrent threads, applicable to multiple steps like crawling, filtering, and summarizing.

#### Highlight: Customizing Your Paper Filtering Criteria (`PAPER_FILTER_PROMPT`)

`PAPER_FILTER_PROMPT` is a prompt template used to guide the Large Language Model in determining whether a paper aligns with your research interests.

**Why customize it?**

The default prompt focuses on "the general reasoning ability of large language models." If your research area is different (e.g., computer vision, multimodality, AI ethics, etc.), **you must modify this prompt** to get accurate filtering results.

**How to customize?**

1.  **Clarify your core objective**: What kind of papers do you want to filter? Define your research scope in one sentence.
2.  **Define positive indicators**: What keywords, concepts, or methods do you want to see?
3.  **Define exclusion criteria**: What fields, technologies, or applications do you explicitly not want?
4.  **Handle ambiguous cases**: For interdisciplinary or borderline papers, provide specific judgment logic.
5.  **Modify `PAPER_FILTER_PROMPT`**: Open `src/utils/config.py` and, referring to the structure of the default template, replace its content with your criteria.

**Customization Example: Suppose your research area is "AI applications in medical imaging"**

You could change `PAPER_FILTER_PROMPT` to:

```python
PAPER_FILTER_PROMPT = """You are a top expert in medical image analysis, screening papers for a research project on "Applications of AI in Medical Image Diagnosis."

My Core Objective:
To filter for papers that apply AI techniques (especially deep learning) to medical imaging (like CT, MRI, X-ray) to improve diagnostic efficiency and accuracy.

Filtering Criteria:

Step 1: Core Judgment
- Keep: The core of the paper is applying AI models to tasks like medical image analysis, lesion detection, image segmentation, or disease classification.
- Exclude: The core of the paper is pure AI theory, model optimization without application to medical imaging, or about non-imaging medical data (like EHR, genetic data).

Step 2: Positive Indicators (the more, the better)
- Core Concepts: Medical Imaging, CT, MRI, X-ray, Ultrasound, Pathology
- Technical Directions: Deep Learning, CNN, Transformer, Segmentation, Detection, Classification
- Application Scenarios: Cancer Diagnosis, Lesion Detection, Image Registration

Step 3: Exclusion Criteria (exclude if it's the main focus)
- Non-imaging Applications: Electronic Health Records (EHR), Genomics, Drug Discovery
- Foundational Model Research: Proposing a general model without sufficient validation on medical imaging.
- Review Papers: If it is purely a review paper rather than proposing a new method or application.

Step 5: Final Decision
Based on the analysis above, please provide your final judgment.

---
Paper Title: {title}
Paper Abstract: {summary}
---

Please respond strictly in the following format:
Result: [True/False]
Reason: [Please explain your judgment process and core rationale in detail in English, based on the screening criteria above.]
"""
```

By customizing it this way, PaperTools can become your exclusive and efficient research assistant.

### Examples

```bash
# Full processing (1000 papers, default)
python papertools.py run

# Quick test (10 papers)
python papertools.py run --mode quick

# Process specific categories
python papertools.py run --categories cs.AI cs.CL

# Process specific date
python papertools.py run --date 2025-09-24

# Custom paper count
python papertools.py run --max-papers-total 500
```

## Project Structure

```
PaperTools/
├── papertools.py              # Main entry point
├── requirements.txt           # Dependencies
├── .env.example              # Environment variable template
├── README.md                 # Chinese documentation
├── README_EN.md              # English documentation
├── src/                      # Source code directory
│   ├── core/                 # Core functionality modules
│   │   ├── pipeline.py       # Main pipeline script
│   │   ├── crawl_arxiv.py    # Paper crawling
│   │   ├── select_.py        # Paper filtering
│   │   ├── generate_summary.py # Summary and inspiration tracing generation
│   │   ├── generate_unified_index.py # Unified web page generation
│   │   └── serve_webpages.py # Local server
│   ├── utils/                # Utilities and configuration
│   │   ├── config.py         # Configuration file
│   │   └── cache_manager.py  # Cache management
│   └── legacy/               # Legacy/experimental code
├── arxiv_paper/              # Crawled raw papers
├── domain_paper/             # Filtered papers
├── summary/                  # Generated summaries
└── webpages/                 # Generated web pages
```

## Contributing

Contributions are welcome! Please feel free to submit Issues and Pull Requests to improve this project.

## Support

For questions or suggestions, please contact us through GitHub Issues.

---

If this project helps you, please give it a star!