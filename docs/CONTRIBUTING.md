# Contributing Guide

## Getting Started

### Prerequisites

| Requirement | Minimum Version |
|---|---|
| CMake | 3.16 |
| Qt | 5.15.0 |
| KDE Frameworks (KF5) | 5.71.0 |
| ICU | 61.0 |
| C++ Compiler | C++17 support (GCC 7+, Clang 5+) |
| Git | Any recent version |

**Install dependencies on Ubuntu/Debian:**
```bash
sudo apt install \
    cmake extra-cmake-modules \
    qtbase5-dev qttools5-dev \
    libkf5config-dev libkf5configwidgets-dev \
    libkf5coreaddons-dev libkf5crash-dev \
    libkf5dbusaddons-dev libkf5globalaccel-dev \
    libkf5guiaddons-dev libkf5i18n-dev \
    libkf5iconthemes-dev libkf5kio-dev \
    libkf5newstuff-dev libkf5notifications-dev \
    libkf5notifyconfig-dev libkf5parts-dev \
    libkf5pty-dev libkf5service-dev \
    libkf5textwidgets-dev libkf5widgetsaddons-dev \
    libkf5windowsystem-dev libkf5xmlgui-dev \
    libkf5bookmarks-dev \
    libicu-dev
```

---

## Building from Source

```bash
# 1. Clone the repository
git clone https://github.com/aamirkhani/konsole-with-projects.git
cd konsole-with-projects

# 2. Create an out-of-source build directory
mkdir build && cd build

# 3. Configure
cmake -DCMAKE_BUILD_TYPE=Debug ..

# 4. Build (use -j<CPU count> for parallel compilation)
make -j$(nproc)

# 5. Run the binary
./bin/konsole-projects
```

### CMake Options

| Option | Default | Description |
|---|---|---|
| `CMAKE_BUILD_TYPE` | `Release` | `Debug`, `Release`, or `RelWithDebInfo` |
| `ENABLE_PLUGIN_SSHMANAGER` | `ON` | Build the SSH Manager plugin |
| `ENABLE_PLUGIN_QUICKCOMMANDS` | `ON` | Build the Quick Commands plugin |
| `INSTALL_ICONS` | `OFF` | Install KDE icon files alongside the binary |
| `WITHOUT_X11` | `OFF` | Build without X11 integration |
| `ECM_ENABLE_SANITIZERS` | — | Enable runtime sanitizers, e.g. `'address;undefined'` |

Example debug build with sanitizers:
```bash
cmake -DCMAKE_BUILD_TYPE=Debug \
      -DECM_ENABLE_SANITIZERS='address;undefined' \
      ..
```

---

## Project Structure

```
konsole-with-projects/
├── CMakeLists.txt               # Root build file
├── README.md                    # User-facing overview
├── INSTALLATION.md              # Installation instructions
├── docs/                        # Developer documentation (this folder)
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── CONTRIBUTING.md
├── install.sh                   # One-liner install script
├── run.sh                       # Helper to launch with bundled libs
├── src/                         # All C++ source code
│   ├── Project.h / .cpp         # Project data model
│   ├── ProjectManager.h / .cpp  # Project lifecycle
│   ├── ViewManager.h / .cpp     # View coordinator (modified)
│   ├── MainWindow.h / .cpp      # Top-level window
│   ├── Application.h / .cpp     # Application entry
│   ├── widgets/
│   │   ├── ProjectTabBar.h / .cpp       # Top tab bar UI
│   │   ├── ProjectHeaderWidget.h / .cpp # Combo-box project UI
│   │   ├── ViewContainer.h / .cpp       # Shell tab container (modified)
│   │   └── ...
│   ├── terminalDisplay/         # Terminal rendering
│   ├── session/                 # PTY sessions
│   ├── profile/                 # User profiles
│   ├── colorscheme/             # Color schemes
│   ├── keyboardtranslator/      # Keyboard mappings
│   ├── history/                 # Scrollback history
│   ├── filterHotSpots/          # URL/link detection
│   ├── plugins/                 # Optional plugins
│   │   ├── SSHManager/
│   │   └── QuickCommands/
│   └── autotests/               # Automated tests
└── data/                        # Icons, color schemes, keyboard maps
```

---

## Coding Conventions

This project follows KDE's coding conventions:

1. **Formatting:** Uses `clang-format` with the KDE style. Run before committing:
   ```bash
   # From the build directory:
   cmake --build . --target clang-format
   ```
   The pre-commit hook (set up automatically by KDE CMake) also enforces this.

2. **Naming:**
   - Classes: `PascalCase`
   - Private member variables: `_camelCase` (underscore prefix)
   - Signals and slots: `camelCase`
   - Public methods: `camelCase`

3. **Headers:** Use `#ifndef / #define / #endif` include guards matching the filename in `SCREAMING_SNAKE_CASE`.

4. **Qt Signals & Slots:** Use the new-style `connect()` syntax:
   ```cpp
   // Preferred
   connect(obj, &ClassName::signal, receiver, &ReceiverClass::slot);
   // Avoid the old SIGNAL/SLOT macro style
   ```

5. **Memory:** Prefer `QPointer<T>` when storing pointers to `QObject` subclasses that may be deleted externally (as done in `Project` and `ProjectManager`).

6. **No `QForeach`:** The build defines `-DQT_NO_FOREACH`; use range-based `for` loops instead.

7. **Strict iterators:** The build defines `-DQT_STRICT_ITERATORS`; do not pass container iterators across container modification.

---

## Adding a New Feature to Project Management

Here is a step-by-step guide for extending the project system.

### Example: Persist Projects Across Sessions

1. **Decide on storage format** — KDE uses `KConfig` / `KConfigGroup`. Add a read/write method to `ProjectManager`.

2. **Add serialisation to `ProjectManager`:**
   ```cpp
   // In ProjectManager.h
   void saveProjects(KConfigGroup &group);
   void loadProjects(const KConfigGroup &group);
   ```

3. **Hook into session save/restore in `ViewManager`:**
   ```cpp
   // ViewManager already has:
   void saveSessions(KConfigGroup &group);
   void restoreSessions(const KConfigGroup &group);
   // Call saveProjects() / loadProjects() from these methods.
   ```

4. **Add unit tests** in `src/autotests/` following the existing test patterns.

5. **Update documentation** in `docs/ARCHITECTURE.md` and `docs/API.md`.

---

## Running Tests

Unit tests live in `src/autotests/`. Build and run them with:

```bash
cd build
make -j$(nproc)
ctest --output-on-failure
```

Or run a specific test:
```bash
ctest -R <test-name> --output-on-failure
```

Tests use the `QTest` framework. Add new tests by:
1. Creating a `.cpp` file in `src/autotests/`.
2. Adding it to `src/autotests/CMakeLists.txt` using `ecm_add_test()`.

---

## Submitting Changes

1. **Fork** the repository on GitHub.
2. **Create a feature branch** from `master`:
   ```bash
   git checkout -b feature/my-feature
   ```
3. **Make your changes**, following the coding conventions above.
4. **Run `clang-format`** to ensure consistent formatting.
5. **Run the tests** and confirm they pass.
6. **Write a clear commit message:**
   ```
   Short summary (≤ 72 characters)

   Longer description of what changed and why.
   Reference any issue numbers with "Fixes #N" or "Closes #N".
   ```
7. **Push** and open a Pull Request against `master`.

---

## Debugging Tips

### Enable Qt Logging

```bash
QT_LOGGING_RULES="konsole.*=true" ./konsole-projects
```

View available Konsole logging categories:
```bash
cat build/konsole.categories
```

### GDB Debugging

```bash
# Build in Debug mode first, then:
gdb --args ./build/bin/konsole-projects
```

### AddressSanitizer

```bash
cmake -DCMAKE_BUILD_TYPE=Debug \
      -DECM_ENABLE_SANITIZERS='address' \
      ..
make -j$(nproc)
./bin/konsole-projects
```

---

## License

All contributions to this project must be licensed under **GPL-2.0-or-later**, matching the existing codebase. Add the SPDX header to every new file:

```cpp
/*
    SPDX-FileCopyrightText: <year> <Your Name>

    SPDX-License-Identifier: GPL-2.0-or-later
*/
```
