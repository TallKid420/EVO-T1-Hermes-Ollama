#!/bin/bash
# Cross-platform installer launcher

# Detect the platform and run the appropriate installer
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    # Windows
    echo "Detected Windows, using Python installer..."
    python install.py --installer
elif [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    echo "Detected macOS, using Python installer..."
    python3 install.py --installer
else
    # Linux/Unix
    echo "Detected Linux/Unix, using Python installer..."
    python3 install.py --installer
fi