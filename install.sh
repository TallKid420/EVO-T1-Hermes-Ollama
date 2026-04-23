#!/bin/bash
# Install dependencies needed for the installer itself
pip install questionary ruamel.yaml rich --user --quiet

# Run the installer script
curl -fsSL https://raw.githubusercontent.com/TallKid420/EVO-T1-Hermes-Ollama/main/install.py | python3