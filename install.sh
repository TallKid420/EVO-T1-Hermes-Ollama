#!/bin/bash
# Install dependencies needed for the installer itself

# Global variable for cleanup
TEMP_VENV=""

# Cleanup function
cleanup() {
    if [ -n "$TEMP_VENV" ] && [ -d "$TEMP_VENV" ]; then
        rm -rf "$TEMP_VENV"
    fi
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Function to install packages handling externally managed environments
install_deps() {
    echo "Installing required dependencies..."

    # Create a temporary virtual environment for the installer
    TEMP_VENV=$(mktemp -d)
    echo "Creating temporary virtual environment at $TEMP_VENV"

    if python3 -m venv "$TEMP_VENV" 2>/dev/null; then
        echo "Virtual environment created successfully"
        # Activate the virtual environment and install packages
        source "$TEMP_VENV/bin/activate"
        if pip install questionary ruamel.yaml rich --quiet; then
            echo "Dependencies installed successfully in virtual environment"
            # Export the venv path so the Python script can use it
            export INSTALLER_VENV="$TEMP_VENV"
            return 0
        else
            echo "Failed to install in virtual environment"
            deactivate
            rm -rf "$TEMP_VENV"
        fi
    fi

    # Fallback: Try --user first (works on some systems)
    if pip install questionary ruamel.yaml rich --user --quiet 2>/dev/null; then
        echo "Dependencies installed successfully with --user"
        return 0
    fi

    # Try system-wide with --break-system-packages (for externally managed environments)
    if pip install questionary ruamel.yaml rich --break-system-packages --quiet 2>/dev/null; then
        echo "Dependencies installed successfully (system-wide)"
        return 0
    fi

    # Try with pipx if available
    if command -v pipx >/dev/null 2>&1; then
        if pipx install questionary ruamel.yaml rich --quiet 2>/dev/null; then
            echo "Dependencies installed successfully with pipx"
            return 0
        fi
    fi

    # Try apt packages if on Ubuntu/Debian
    if command -v apt >/dev/null 2>&1; then
        echo "Trying to install system packages..."
        if apt update --quiet && apt install -y --quiet python3-questionary python3-ruamel.yaml python3-rich 2>/dev/null; then
            echo "Dependencies installed successfully via apt"
            return 0
        fi
    fi

    echo "Failed to install dependencies automatically."
    echo "Please install manually: pip install questionary ruamel.yaml rich"
    echo "Or on Ubuntu/Debian: apt install python3-questionary python3-ruamel.yaml python3-rich"
    exit 1
}

install_deps

# Run the installer script
echo "Running Hermes installer..."
if [ -n "$INSTALLER_VENV" ]; then
    # Use the virtual environment's Python
    curl -fsSL https://raw.githubusercontent.com/TallKid420/EVO-T1-Hermes-Ollama/main/install.py | "$INSTALLER_VENV/bin/python3"
else
    # Use system Python
    curl -fsSL https://raw.githubusercontent.com/TallKid420/EVO-T1-Hermes-Ollama/main/install.py | python3
fi