/*
    SPDX-FileCopyrightText: 2026 Konsole Contributors

    SPDX-License-Identifier: GPL-2.0-or-later
*/

#ifndef PROJECTTABBAR_H
#define PROJECTTABBAR_H

#include <QTabBar>

namespace Konsole
{
class ProjectManager;
class Project;

/**
 * A custom tab bar for displaying and switching between projects.
 * Shows project names as tabs and emits signals when tabs are activated.
 */
class ProjectTabBar : public QTabBar
{
    Q_OBJECT

public:
    /**
     * Constructs a new project tab bar.
     */
    explicit ProjectTabBar(ProjectManager *manager, QWidget *parent = nullptr);

    /**
     * Refresh the tab bar to show current projects.
     */
    void refresh();

    /**
     * Rename a project.
     */
    void renameProject(Project *project, const QString &newName);

protected:
    void contextMenuEvent(QContextMenuEvent *event) override;
    void mouseDoubleClickEvent(QMouseEvent *event) override;

Q_SIGNALS:
    /**
     * Emitted when a project tab is clicked.
     */
    void projectActivated(Project *project);

    /**
     * Emitted when the "+" button is clicked to create new project.
     */
    void newProjectRequested();

private Q_SLOTS:
    void onProjectCreated(Project *project);
    void onProjectRemoved(Project *project);
    void onActiveProjectChanged(Project *project);
    void onTabClicked(int index);
    void onRenameProjectTriggered();

private:
    void setupUI();

    ProjectManager *_projectManager = nullptr;
    QHash<int, Project *> _tabToProject;
    int _projectButtonIndex = -1;
};

}

#endif // PROJECTTABBAR_H
