# Installation & Usage Guide

## Quick Start

### Option 1: Download & Run (Easiest)
```bash
# Download the binary
wget https://github.com/aamirkhani/konsole-with-projects/raw/master/konsole-projects

# Make it executable
chmod +x konsole-projects

# Run it
./konsole-projects
```

### Option 2: Install to System PATH
```bash
# Download
wget https://github.com/aamirkhani/konsole-with-projects/raw/master/konsole-projects

# Install to /usr/local/bin
sudo cp konsole-projects /usr/local/bin/

# Make executable
sudo chmod +x /usr/local/bin/konsole-projects

# Run from anywhere
konsole-projects
```

### Option 3: Use Setup Script
```bash
# Download and run the setup script
bash <(curl -fsSL https://raw.githubusercontent.com/aamirkhani/konsole-with-projects/master/install.sh)
```

## Features

This is a modified version of KDE Konsole with **Project Management**:

- **Project Tabs** at the top level for organizing related terminals
- **Shell Tabs** below showing terminals within the active project
- **Auto-filter**: Only shows tabs belonging to the active project
- **Smart Navigation**: 
  - Ctrl+PageUp/PageDown navigates within project tabs
  - At project boundaries, switches to adjacent project
  - Ctrl+1 through Ctrl+9 for direct project access
- **Rename Projects**: Right-click or double-click project tabs
- **Auto First Tab**: Each new project gets a terminal automatically

## Naming

- Binary is named `konsole-projects` to **avoid conflicts** with the standard KDE Konsole
- Your original Konsole remains unchanged
- Both can run simultaneously

## Requirements

- Ubuntu 20.04+ / Debian 10+ / Any Linux with Qt 5.15+
- KDE Frameworks 5.80+ (usually pre-installed)

## Compatibility

- Fully compatible with your existing Konsole settings
- Reads/writes to the same config files as standard Konsole
- No installation required - just run the binary

## Uninstall

If installed to `/usr/local/bin/`:
```bash
sudo rm /usr/local/bin/konsole-projects
```

Otherwise, just delete the binary file.

## Building from Source

```bash
git clone https://github.com/aamirkhani/konsole-with-projects.git
cd konsole-with-projects
mkdir build && cd build
cmake ..
make -j4
./bin/konsole-projects
```

## Troubleshooting

**Binary won't start**: Ensure you have KDE Frameworks installed:
```bash
sudo apt install kdelibs5-bin kdelibs4support
```

**Missing libraries**: Run with full path:
```bash
ldd ./konsole-projects
```

## License

KDE Konsole - LGPL v2+

