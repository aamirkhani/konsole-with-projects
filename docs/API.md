# API Reference

This document describes the public API of the project-management classes added to Konsole with Projects. For the upstream Konsole API, refer to the [KDE Konsole source documentation](https://invent.kde.org/utilities/konsole).

All classes are in the `Konsole` namespace.

---

## `Project`

**Header:** `src/Project.h`
**Base class:** `QObject`
**Purpose:** Data model representing a single project that groups one or more terminal tabs.

### Constructor

```cpp
explicit Project(const QString &name = QString(), QObject *parent = nullptr);
```

Creates a new project. If `name` is empty, the project will have no name until one is assigned. Each project receives a unique integer ID upon construction.

### Properties

#### `name() / setName()`

```cpp
QString name() const;
void setName(const QString &name);
```

The human-readable display name of the project. Calling `setName()` emits `nameChanged(QString)`.

#### `id()`

```cpp
int id() const;
```

Returns the unique, auto-incremented integer ID assigned at construction. IDs are never reused within a process lifetime.

### Terminal Management

#### `addTerminal()`

```cpp
void addTerminal(TerminalDisplay *terminal);
```

Associates a `TerminalDisplay` widget with this project. Emits `terminalAdded(TerminalDisplay*)`.

#### `removeTerminal()`

```cpp
void removeTerminal(TerminalDisplay *terminal);
```

Disassociates a terminal from this project. Emits `terminalRemoved(TerminalDisplay*)`.

#### `terminals()`

```cpp
QList<QPointer<TerminalDisplay>> terminals() const;
```

Returns all terminals currently associated with this project. Entries may be null if a terminal widget was destroyed; callers should check before dereferencing.

#### `terminalCount()`

```cpp
int terminalCount() const;
```

Returns the number of terminal entries (including any that may have been destroyed).

### Signals

| Signal | Description |
|---|---|
| `nameChanged(const QString &name)` | Emitted after the project name is changed. |
| `terminalAdded(TerminalDisplay *terminal)` | Emitted when a terminal is added. |
| `terminalRemoved(TerminalDisplay *terminal)` | Emitted when a terminal is removed. |

---

## `ProjectManager`

**Header:** `src/ProjectManager.h`
**Base class:** `QObject`
**Purpose:** Lifecycle manager for a collection of `Project` objects. Tracks the active project and enforces unique names.

### Constructor / Destructor

```cpp
explicit ProjectManager(QObject *parent = nullptr);
~ProjectManager() override;
```

### Project Creation & Removal

#### `createProject()`

```cpp
Project *createProject(const QString &name = QString());
```

Creates a new project and adds it to the managed list. If `name` is empty, a default name is generated ("Project 1", "Project 2", …, incrementing a counter). Emits `projectCreated(Project*)`. The `ProjectManager` takes ownership of the returned `Project`.

#### `removeProject()`

```cpp
bool removeProject(Project *project);
```

Removes a project from the managed list and deletes it. Returns `true` on success, `false` if the project was not found. Emits `projectRemoved(Project*)`.

### Lookup

#### `projectAt()`

```cpp
Project *projectAt(int index) const;
```

Returns the project at the given zero-based index, or `nullptr` if out of range.

#### `projectByName()`

```cpp
Project *projectByName(const QString &name) const;
```

Returns the first project whose name matches `name`, or `nullptr` if none.

#### `projectForTerminal()`

```cpp
Project *projectForTerminal(QObject *terminal) const;
```

Searches all projects for one that contains `terminal`. Returns the owning `Project`, or `nullptr`.

#### `projects()`

```cpp
QList<QPointer<Project>> projects() const;
```

Returns all managed projects in creation order.

#### `projectCount()`

```cpp
int projectCount() const;
```

Returns the total number of managed projects.

### Active Project

#### `activeProject()`

```cpp
Project *activeProject() const;
```

Returns the currently active project, or `nullptr` if none has been set.

#### `setActiveProject()`

```cpp
void setActiveProject(Project *project);
```

Changes the active project. Emits `activeProjectChanged(Project*)` if the project actually changed.

### Signals

| Signal | Description |
|---|---|
| `projectCreated(Project *project)` | Emitted after a new project is created. |
| `projectRemoved(Project *project)` | Emitted just before a project is destroyed. |
| `activeProjectChanged(Project *project)` | Emitted when the active project changes. |

---

## `ProjectTabBar`

**Header:** `src/widgets/ProjectTabBar.h`
**Base class:** `QTabBar`
**Purpose:** Visual tab bar at the top of the window for displaying and switching between projects.

### Constructor

```cpp
explicit ProjectTabBar(ProjectManager *manager, QWidget *parent = nullptr);
```

Creates the tab bar and connects to the given `ProjectManager` to stay in sync. The tab bar does not take ownership of `manager`.

### Methods

#### `refresh()`

```cpp
void refresh();
```

Rebuilds all tabs from the current state of the `ProjectManager`. Call this after bulk changes to the project list.

#### `renameProject()`

```cpp
void renameProject(Project *project, const QString &newName);
```

Renames `project` to `newName` and updates the tab label.

### Interactions

- **Left-click** a project tab → emits `projectActivated(Project*)`.
- **Left-click** the "+" tab → emits `newProjectRequested()`.
- **Right-click** a project tab → shows a context menu with "Rename Project…".
- **Double-click** a project tab → opens an inline rename dialog.

### Signals

| Signal | Description |
|---|---|
| `projectActivated(Project *project)` | User clicked a project tab; the caller should make this project active. |
| `newProjectRequested()` | User clicked the "+" tab; the caller should create a new project. |

---

## `ProjectHeaderWidget`

**Header:** `src/widgets/ProjectHeaderWidget.h`
**Base class:** `QWidget`
**Purpose:** Alternative combo-box UI for project selection. Can be embedded in toolbars or headers.

### Constructor

```cpp
explicit ProjectHeaderWidget(ProjectManager *manager, QWidget *parent = nullptr);
```

Initialises the widget and populates it from the given `ProjectManager`.

### Methods

#### `refreshProjects()`

```cpp
void refreshProjects();
```

Repopulates the combo box from the current project list.

#### `updateCurrentProject()`

```cpp
void updateCurrentProject();
```

Scrolls/selects the combo box entry that matches `ProjectManager::activeProject()`.

### Signals

| Signal | Description |
|---|---|
| `projectSelected(Project *project)` | The user selected a different project from the combo box. |

---

## `ViewManager` (project-related API)

**Header:** `src/ViewManager.h`
**Purpose:** Coordinates terminal views and integrates project management into the window.

The full `ViewManager` API is large; the additions specific to project management are:

### D-Bus Interface: `org.kde.konsole.Window`

The following D-Bus slots exist (unchanged from upstream, but listed for reference):

| Slot | Return | Description |
|---|---|---|
| `sessionCount()` | `int` | Number of sessions in the active view |
| `sessionList()` | `QStringList` | Ordered list of session IDs |
| `currentSession()` | `int` | Active session ID |
| `setCurrentSession(int)` | `void` | Switch to session by ID |
| `newSession()` | `int` | Create session with default profile |
| `newSession(QString)` | `int` | Create session with named profile |
| `newSession(QString, QString)` | `int` | Create session with profile + working dir |
| `nextSession()` | `void` | Switch to next session |
| `prevSession()` | `void` | Switch to previous session |

### Navigation Method Enum

```cpp
enum NavigationMethod {
    TabbedNavigation,  // Standard tab bar (default)
    NoNavigation,      // No navigation widget
};
```

### Navigation Visibility Enum

```cpp
enum NavigationVisibility {
    NavigationNotSet,
    AlwaysShowNavigation,
    ShowNavigationAsNeeded,
    AlwaysHideNavigation,
};
```

---

## Keyboard Shortcuts Summary

| Shortcut | Action | Implemented In |
|---|---|---|
| `Ctrl+1` … `Ctrl+9` | Switch to project 1–9 | `ViewManager` (QShortcut) |
| `Ctrl+PageDown` | Next shell tab (crosses project boundary) | `ViewManager::nextView()` |
| `Ctrl+PageUp` | Previous shell tab (crosses project boundary) | `ViewManager::previousView()` |
| Right-click project tab | Context menu → Rename | `ProjectTabBar::contextMenuEvent()` |
| Double-click project tab | Inline rename | `ProjectTabBar::mouseDoubleClickEvent()` |
| Click "+" tab | Create new project | `ProjectTabBar` → `newProjectRequested()` |
