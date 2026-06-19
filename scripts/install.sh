#!/usr/bin/env bash
# OMEGA Installation Script
set -euo pipefail

OMEGA_VERSION="1.0.0"
PYTHON_MIN_VERSION="3.10"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_banner() {
    echo -e "${CYAN}"
    echo " ██████╗ ███╗   ███╗███████╗ ██████╗  █████╗ "
    echo "██╔═══██╗████╗ ████║██╔════╝██╔════╝ ██╔══██╗"
    echo "██║   ██║██╔████╔██║█████╗  ██║  ███╗███████║"
    echo "██║   ██║██║╚██╔╝██║██╔══╝  ██║   ██║██╔══██║"
    echo "╚██████╔╝██║ ╚═╝ ██║███████╗╚██████╔╝██║  ██║"
    echo " ╚═════╝ ╚═╝     ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝"
    echo -e "${NC}"
    echo "Installing OMEGA v${OMEGA_VERSION}..."
    echo ""
}

check_python() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Error: python3 not found. Please install Python ${PYTHON_MIN_VERSION}+${NC}"
        exit 1
    fi
    PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo -e "${GREEN}✓${NC} Found Python ${PYVER}"
}

setup_venv() {
    echo -e "${CYAN}Setting up virtual environment...${NC}"
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install --upgrade pip -q
    echo -e "${GREEN}✓${NC} Virtual environment ready"
}

install_deps() {
    echo -e "${CYAN}Installing dependencies (this may take a few minutes)...${NC}"
    pip install -r requirements.txt -q
    echo -e "${GREEN}✓${NC} Python dependencies installed"

    echo -e "${CYAN}Installing Playwright browsers...${NC}"
    python -m playwright install chromium --with-deps 2>/dev/null || python -m playwright install chromium
    echo -e "${GREEN}✓${NC} Browser automation ready"
}

install_package() {
    echo -e "${CYAN}Installing OMEGA package...${NC}"
    pip install -e . -q
    echo -e "${GREEN}✓${NC} OMEGA installed"
}

setup_config() {
    echo -e "${CYAN}Setting up configuration...${NC}"
    if [ ! -f ".env" ]; then
        cp .env.example .env
        echo -e "${YELLOW}⚠ Created .env file. Please edit it and add your OPENROUTER_API_KEY${NC}"
        echo -e "${YELLOW}  Get a free key at: https://openrouter.ai/keys${NC}"
    else
        echo -e "${GREEN}✓${NC} .env already exists"
    fi

    mkdir -p ~/.omega/{plugins,memory,logs,sandbox,workflows}
    echo -e "${GREEN}✓${NC} OMEGA home directory created at ~/.omega"
}

check_optional_services() {
    echo ""
    echo -e "${CYAN}Checking optional services...${NC}"

    if command -v docker &> /dev/null; then
        echo -e "${GREEN}✓${NC} Docker found (enables sandboxed code execution)"
    else
        echo -e "${YELLOW}⚠${NC} Docker not found (code will run via subprocess fallback)"
    fi

    if command -v redis-cli &> /dev/null && redis-cli ping &> /dev/null; then
        echo -e "${GREEN}✓${NC} Redis found and running (enables task queue)"
    else
        echo -e "${YELLOW}⚠${NC} Redis not found/running (some background features limited)"
        echo -e "  ${YELLOW}Install with: docker run -d -p 6379:6379 redis:7-alpine${NC}"
    fi
}

main() {
    print_banner
    check_python
    setup_venv
    install_deps
    install_package
    setup_config
    check_optional_services

    echo ""
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}  OMEGA installation complete!${NC}"
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Edit .env and add your OpenRouter API key"
    echo "  2. Activate the virtual environment: source .venv/bin/activate"
    echo "  3. Run OMEGA: omega run"
    echo ""
    echo "Or start the API server: omega serve"
    echo ""
}

main "$@"
