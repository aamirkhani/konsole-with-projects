/*
    SPDX-FileCopyrightText: 2026 Konsole Contributors

    SPDX-License-Identifier: GPL-2.0-or-later
*/

#include "ProjectTabBar.h"
#include "Project.h"
#include "ProjectManager.h"

#include <QHash>
#include <QContextMenuEvent>
#include <QMenu>
#include <QInputDialog>
#include <QLineEdit>
#include <QMouseEvent>

using namespace Konsole;

ProjectTabBar::ProjectTabBar(ProjectManager *manager, QWidget *parent)
    : QTabBar(parent)
    , _projectManager(manager)
{
    if (_projectManager) {
        connect(_projectManager, &ProjectManager::projectCreated, this, &ProjectTabBar::onProjectCreated);
        connect(_projectManager, &ProjectManager::projectRemoved, this, &ProjectTabBar::onProjectRemoved);
        connect(_projectManager, &ProjectManager::activeProjectChanged, this, &ProjectTabBar::onActiveProjectChanged);
        connect(this, QOverload<int>::of(&QTabBar::currentChanged), this, &ProjectTabBar::onTabClicked);
    }
    
    refresh();
}

void ProjectTabBar::refresh()
{
    if (!_projectManager) {
        return;
    }
    
    blockSignals(true);
    while (count() > 0) {
        removeTab(0);
    }
    _tabToProject.clear();
    
    int activeIndex = 0;
    Project *activeProject = _projectManager->activeProject();
    
    // Add tabs for each project
    for (int i = 0; i < _projectManager->projectCount(); ++i) {
        Project *proj = _projectManager->projectAt(i);
        if (proj) {
            int tabIndex = addTab(proj->name());
            _tabToProject[tabIndex] = proj;
            
            if (proj == activeProject) {
                activeIndex = tabIndex;
            }
        }
    }
    
    // Add "+" button as a tab
    _projectButtonIndex = addTab(QStringLiteral("+"));
    
    setCurrentIndex(activeIndex);
    blockSignals(false);
}

void ProjectTabBar::onProjectCreated(Project *project)
{
    refresh();
}

void ProjectTabBar::onProjectRemoved(Project *project)
{
    refresh();
}

void ProjectTabBar::onActiveProjectChanged(Project *project)
{
    if (!project || !_projectManager) {
        return;
    }
    
    // Find and select the tab for this project
    for (int i = 0; i < _projectManager->projectCount(); ++i) {
        Project *proj = _projectManager->projectAt(i);
        if (proj == project) {
            blockSignals(true);
            setCurrentIndex(i);
            blockSignals(false);
            break;
        }
    }
}

void ProjectTabBar::onTabClicked(int index)
{
    if (!_projectManager) {
        return;
    }
    
    // Check if "+" button was clicked
    if (index == _projectButtonIndex) {
        Q_EMIT newProjectRequested();
        // Reset to previous project
        Project *activeProject = _projectManager->activeProject();
        if (activeProject) {
            blockSignals(true);
            for (int i = 0; i < _projectManager->projectCount(); ++i) {
                if (_projectManager->projectAt(i) == activeProject) {
                    setCurrentIndex(i);
                    break;
                }
            }
            blockSignals(false);
        }
        return;
    }
    
    // Switch to selected project
    if (_tabToProject.contains(index)) {
        Project *project = _tabToProject[index];
        _projectManager->setActiveProject(project);
        Q_EMIT projectActivated(project);
    }
}

void ProjectTabBar::contextMenuEvent(QContextMenuEvent *event)
{
    int tabIndex = tabAt(event->pos());
    
    // Don't show menu for "+" button
    if (tabIndex < 0 || tabIndex == _projectButtonIndex) {
        return;
    }
    
    if (!_tabToProject.contains(tabIndex)) {
        return;
    }
    
    Project *project = _tabToProject[tabIndex];
    
    QMenu menu;
    QAction *renameAction = menu.addAction(QStringLiteral("Rename Project..."));
    
    QAction *selected = menu.exec(event->globalPos());
    if (selected == renameAction) {
        onRenameProjectTriggered();
    }
}

void ProjectTabBar::mouseDoubleClickEvent(QMouseEvent *event)
{
    int tabIndex = tabAt(event->pos());
    
    // Don't allow renaming "+" button
    if (tabIndex < 0 || tabIndex == _projectButtonIndex) {
        return;
    }
    
    if (_tabToProject.contains(tabIndex)) {
        Project *project = _tabToProject[tabIndex];
        
        bool ok;
        QString newName = QInputDialog::getText(
            this,
            QStringLiteral("Rename Project"),
            QStringLiteral("New name:"),
            QLineEdit::Normal,
            project->name(),
            &ok
        );
        
        if (ok && !newName.isEmpty() && newName != project->name()) {
            renameProject(project, newName);
        }
    }
    
    QTabBar::mouseDoubleClickEvent(event);
}

void ProjectTabBar::onRenameProjectTriggered()
{
    int idx = QTabBar::currentIndex();
    
    // Don't allow renaming "+" button
    if (idx < 0 || idx == _projectButtonIndex) {
        return;
    }
    
    if (_tabToProject.contains(idx)) {
        Project *project = _tabToProject[idx];
        
        bool ok;
        QString newName = QInputDialog::getText(
            this,
            QStringLiteral("Rename Project"),
            QStringLiteral("New name:"),
            QLineEdit::Normal,
            project->name(),
            &ok
        );
        
        if (ok && !newName.isEmpty() && newName != project->name()) {
            renameProject(project, newName);
        }
    }
}

void ProjectTabBar::renameProject(Project *project, const QString &newName)
{
    if (!project || newName.isEmpty()) {
        return;
    }
    
    project->setName(newName);
    refresh();
}
