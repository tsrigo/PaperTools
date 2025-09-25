# PaperTools

English | [中文](README.md)

PaperTools is a comprehensive academic paper processing pipeline that provides automated paper crawling, intelligent filtering, summarization, and web generation capabilities.

## Features

- **Automated Crawling**: Crawl latest papers from arXiv and other academic platforms
- **AI-Powered Filtering**: Use large language models to intelligently filter papers by research domain
- **Automatic Summarization**: Generate high-quality Chinese summaries using jinja.ai for full paper content
- **Web Generation**: Convert papers into interactive HTML pages with modern design
- **Local Deployment**: One-click local server startup for browsing and sharing
- **Multi-threaded Processing**: All components support parallel processing for improved performance
- **Interactive Features**: Support for paper bookmarking, read status tracking, and deletion with persistent storage

## Requirements

- Python 3.7+
- Network connection (for API calls and content retrieval)
- Recommended: 4GB+ RAM (for processing large volumes of papers)

## Installation

### Setup Environment

```bash
# 1. Copy configuration template
cp .env.example .env

# 2. Edit .env file and set your API key
# OPENAI_API_KEY=your_actual_api_key_here
# OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# MODEL=glm-4.5-flash

# 3. Check and install dependencies
python papertools.py check
```

### Quick Start

```bash
# Full mode: process 1000 papers (default)
python papertools.py run

# Quick mode: process 10 papers  
python papertools.py run --mode quick

# View results
python papertools.py serve

# Get help
python papertools.py --help
```

## Usage

### Main Commands

```bash
# Run paper processing pipeline
python papertools.py run [options]
  --mode {quick,full}     # Processing mode: quick(10 papers) or full(1000 papers, default)
  --date YYYY-MM-DD       # Process papers from specific date
  --categories cs.AI cs.CL # Specify paper categories
  --max-papers-total N    # Custom paper count

# Start web server
python papertools.py serve

# Clean cache files  
python papertools.py clean

# Check environment and dependencies
python papertools.py check
```

### Advanced: Individual Module Usage

For using individual modules:

```bash
# 1. Crawl papers
python src/core/crawl_arxiv.py --categories cs.AI cs.CV --max-papers 100

# 2. Filter papers
python src/core/select_.py --input-file arxiv_paper/papers.json

# 3. Generate summaries  
python src/core/generate_summary.py --input-file domain_paper/filtered_papers.json

# 4. Generate web pages
python src/core/generate_webpage.py --input-file domain_paper/filtered_papers.json

# 5. Start server
python src/core/serve_webpages.py --port 8080
```

## Configuration

### Environment Variables

Configure in `.env` file:

```bash
# API Configuration
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
MODEL=glm-4.5-flash

# Optional: Jina API Token (for full paper content retrieval)
JINA_API_TOKEN=your_jina_token_here
```

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
│   │   ├── generate_summary.py # Summary generation
│   │   ├── generate_webpage.py # Web page generation
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

## Use Cases

**AI Research**
- Track latest developments in LLM and reasoning technologies
- Research agent and multi-agent systems
- Understand reinforcement learning applications in AI
- Explore tool usage and evolutionary algorithms

**Academic Research**
- Quickly understand latest developments in specific fields
- Generate paper summaries for literature reviews
- Create elegant paper presentation pages
- Build personal research knowledge bases

**Teaching Support**
- Provide AI frontier paper comprehension assistance for students
- Create course-related paper resource libraries
- Make interactive learning materials
- Show research field development trajectories

**Team Collaboration**
- Share team-focused AI papers
- Unified paper management and display
- Facilitate team discussions and comments
- Track competitors and related work

## Troubleshooting

### Environment Check
```bash
# Check environment and dependencies
python papertools.py check
```

### Common Issues

**API Call Failures**
```bash
# Check API key configuration
cat .env
# Ensure OPENAI_API_KEY is properly set
```

**Missing Dependencies**
```bash
# Auto-install missing dependencies
python papertools.py check
# Or install manually
pip install -r requirements.txt
```

**Web Server Startup Failures**
```bash
# Generate web content first
python papertools.py run
# Then start server
python papertools.py serve
```

**Cache Issues**
```bash
# Clean all cache files
python papertools.py clean
```

### Debug Mode
```bash
# Test with few papers
python papertools.py run --max-papers-total 10

# Quick mode test
python papertools.py run --mode quick
```

## License

MIT License

## Contributing

We welcome contributions! Please feel free to submit Issues and Pull Requests to improve this project.

## Support

For questions or suggestions, please contact us through GitHub Issues.

---

If this project helps you, please give it a star!