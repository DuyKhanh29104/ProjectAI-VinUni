#!/bin/bash
# Setup script cho AI20K project

set -e

echo "=== AI20K Project Setup ==="

# Check Python version
python3 -c "import sys; assert sys.version_info >= (3, 12), 'Python 3.12+ required'"
echo "Python version OK"

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the project, optional local runtimes, and development tools.
python -m pip install --upgrade pip
python -m pip install -e ".[agent,ingestion]" --group dev

# Create .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env — please edit with your API keys"
fi

# Create data directories
mkdir -p data/chroma

echo "Setup complete! Run: uvicorn src.main:app --reload"
