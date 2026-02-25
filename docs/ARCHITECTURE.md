# Architecture Overview

## Project Summary

**Konsole with Projects** is a fork of [KDE Konsole 22.12](https://invent.kde.org/utilities/konsole) that adds a project-based tab organization layer on top of the standard terminal emulator. It introduces a two-level tab hierarchy: **projects** at the top and **shell tabs** below, allowing users to group related terminals together.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MainWindow (KXmlGuiWindow)            │
│  ┌──────────────────────────────────────────────────┐   │
│  │              ViewManager                         │   │
│  │  ┌────────────────────────────────────────────┐  │   │
│  │  │           ProjectTabBar (top bar)          │  │   │
│  │  │  [Main] [Project 1] [Project 2] [+]        │  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  │  ┌────────────────────────────────────────────┐  │   │
│  │  │         TabbedViewContainer (shell tabs)   │  │   │
│  │  │  [Tab 1] [Tab 2] [Tab 3]  (filtered)      │  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  │  ┌────────────────────────────────────────────┐  │   │
│  │  │       TerminalDisplay (active terminal)    │  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘

Data Layer:
  ProjectManager ──manages──► Project[]
  Project ──contains──► TerminalDisplay[]
  ViewManager ──uses──► ProjectManager
```

---

## Component Breakdown

### New Components (Project Management Layer)

#### `Project` (`src/Project.h`, `src/Project.cpp`)
The core data model for a project.

- Stores a **name** and **unique ID** (auto-incremented via static `_nextId`).
- Holds a list of `QPointer<TerminalDisplay>` for the terminals associated with it.
- Emits signals when the name changes or terminals are added/removed.
- Uses `QPointer` to safely handle terminal widget deletion.

#### `ProjectManager` (`src/ProjectManager.h`, `src/ProjectManager.cpp`)
Manages the lifecycle of all projects.

- Creates projects with auto-generated names ("Project 1", "Project 2", …) when no name is provided.
- Tracks the **active project** and broadcasts changes via `activeProjectChanged(Project*)`.
- Provides lookup by index, by name, or by terminal widget.
- Owns all `Project` instances.

#### `ProjectTabBar` (`src/widgets/ProjectTabBar.h`, `src/widgets/ProjectTabBar.cpp`)
A custom `QTabBar` subclass used as the top-level project switcher.

- Adds one tab per project plus a "+" tab to create new projects.
- Responds to right-click (context menu → "Rename Project…") and double-click for inline renaming.
- Connects to `ProjectManager` signals to stay synchronized with the data model.
- Maps tab indices to `Project*` via `_tabToProject` hash.

#### `ProjectHeaderWidget` (`src/widgets/ProjectHeaderWidget.h`, `src/widgets/ProjectHeaderWidget.cpp`)
An alternative/supplementary widget (combo-box style) for project switching.

- Contains a `QComboBox` listing all projects plus a "New Project" button.
- Emits `projectSelected(Project*)` when the user changes the selection.

---

### Modified Components

#### `ViewManager` (`src/ViewManager.h`, `src/ViewManager.cpp`)
Central coordinator for all terminal views in a window.

**Project-related additions:**
- Owns a `ProjectManager` instance.
- Integrates the `ProjectTabBar` into the window layout above the shell tab bar.
- Sets up `Ctrl+1` through `Ctrl+9` shortcuts for direct project switching.
- Sets up `Ctrl+PageUp` / `Ctrl+PageDown` for project-aware tab navigation (crossing project boundaries when at the edge of a project's tabs).
- Assigns new `TerminalDisplay` widgets to the active project when created.

**Core responsibilities (unchanged from upstream):**
- Creates and destroys `TerminalDisplay` widgets.
- Maintains the `_sessionMap` (`TerminalDisplay*` → `Session*`).
- Handles view splitting (left/right, top/bottom).
- Exposes a D-Bus interface (`org.kde.konsole.Window`).

#### `TabbedViewContainer` / `ViewContainer` (`src/ViewContainer.h`, `src/ViewContainer.cpp`)
The shell-tab bar widget.

**Project-related additions:**
- Maintains a mapping of `TerminalDisplay*` → `Project*`.
- Calls `QTabBar::setTabVisible()` to show only the tabs belonging to the active project.
- Filters tabs dynamically whenever the active project changes.

---

### Upstream Components (Unchanged or Minimally Modified)

| Component | Location | Role |
|---|---|---|
| `Session` | `src/session/Session.h` | PTY session, process lifecycle |
| `SessionManager` | `src/session/SessionManager.h` | Session creation & profile application |
| `SessionController` | `src/session/SessionController.h` | Connects Session ↔ TerminalDisplay, provides menus |
| `TerminalDisplay` | `src/terminalDisplay/TerminalDisplay.h` | Renders terminal output, handles input |
| `Emulation` / `Vt102Emulation` | `src/Emulation.h`, `src/Vt102Emulation.h` | VT102/xterm escape sequence processing |
| `Screen` | `src/Screen.h` | In-memory character grid for the terminal |
| `Profile` / `ProfileManager` | `src/profile/` | User-configurable terminal profiles |
| `MainWindow` | `src/MainWindow.h` | Top-level KDE window |
| `Application` | `src/Application.h` | Application startup and session restore |
| `BookmarkHandler` | `src/BookmarkHandler.h` | KDE bookmark integration |
| `Part` | `src/Part.h` | KParts integration for embedding Konsole |

---

## Data Flow

### Creating a New Project
```
User clicks "+" tab
  → ProjectTabBar::onTabClicked()
    → emit newProjectRequested()
      → ViewManager slot
        → ProjectManager::createProject()
          → emit projectCreated(Project*)
            → ProjectTabBar refreshes (adds tab)
            → ViewManager creates first TerminalDisplay
              → assigns it to the new Project
              → Project::addTerminal()
```

### Switching Active Project
```
User clicks project tab (or presses Ctrl+N)
  → ProjectTabBar::onTabClicked()  (or QShortcut trigger)
    → emit projectActivated(Project*)
      → ViewManager::setActiveProject()
        → ProjectManager::setActiveProject()
          → emit activeProjectChanged(Project*)
            → TabbedViewContainer filters tab visibility
            → ProjectTabBar highlights correct tab
```

### Tab Navigation (Ctrl+PageDown)
```
User presses Ctrl+PageDown
  → ViewManager::nextView()
    → checks if there is a next tab in the current project
      → if yes: activate that tab
      → if no (at boundary): switch to next project
          → activate that project's first tab
```

---

## Build System

The project uses **CMake** with KDE's **Extra CMake Modules (ECM)**:

```
CMakeLists.txt          ← root: version, dependencies, subdirs
└── src/
    ├── CMakeLists.txt  ← builds konsoleprivate (shared lib) and konsole-projects (executable)
    │   ├── Project.cpp / ProjectManager.cpp
    │   ├── widgets/ProjectTabBar.cpp / ProjectHeaderWidget.cpp
    │   └── ... (all other source files)
    ├── session/
    ├── terminalDisplay/
    ├── profile/
    ├── plugins/
    │   ├── SSHManager/
    │   └── QuickCommands/
    └── autotests/
```

### Key Build Targets

| Target | Type | Description |
|---|---|---|
| `konsoleprivate` | Shared library (`.so.1`) | Core terminal engine, shared by app and KParts |
| `konsoleapp` | Shared library (`.so.1`) | Application-level code |
| `konsole-projects` | Executable | The modified Konsole binary |

The bundled prebuilt binaries (`libkonsoleapp.so.1`, `libkonsoleprivate.so.1`, `konsole-projects`) allow running without a full KDE build environment, provided KDE Frameworks 5 is installed.

---

## Key Design Decisions

1. **`QPointer` for terminal references** — `Project` stores terminals as `QPointer<TerminalDisplay>` to automatically null-out when widgets are deleted, preventing dangling pointer bugs.

2. **Tab visibility over removal** — Rather than removing shell tabs from `TabbedViewContainer` when switching projects, tabs are hidden via `QTabBar::setTabVisible()`. This preserves tab order and avoids complex re-insertion logic.

3. **Session-scoped projects** — Projects are not persisted to disk. They exist only for the lifetime of the Konsole window, keeping the implementation simple and avoiding config-file schema changes.

4. **Minimal upstream changes** — The project-management feature is implemented as an additive layer with focused modifications to `ViewManager` and `ViewContainer`, minimising merge conflicts when rebasing on future Konsole releases.

5. **Separate binary name** — The binary is named `konsole-projects` (not `konsole`) so it can coexist with the system Konsole without conflicts.
