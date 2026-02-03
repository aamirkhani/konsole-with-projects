#!/bin/bash
set -e

echo "=== Konsole with Project Management Installer ==="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Download binary
echo -e "${BLUE}[1/3]${NC} Downloading konsole-projects binary..."
wget -q https://github.com/aamirkhani/konsole-with-projects/raw/master/konsole-projects
chmod +x konsole-projects

# Determine install location
if [ "$1" = "--local" ] || [ ! -w /usr/local/bin ]; then
    echo -e "${BLUE}[2/3]${NC} Installing to current directory..."
    echo "Binary: ./konsole-projects"
    echo -e "${GREEN}[3/3]${NC} Done! Run with: ${GREEN}./konsole-projects${NC}"
else
    echo -e "${BLUE}[2/3]${NC} Installing to /usr/local/bin..."
    sudo cp konsole-projects /usr/local/bin/
    sudo chmod +x /usr/local/bin/konsole-projects
    rm konsole-projects
    echo -e "${GREEN}[3/3]${NC} Done! Run with: ${GREEN}konsole-projects${NC}"
fi

echo ""
echo "For usage and features, see: https://github.com/aamirkhani/konsole-with-projects"
