/*
    SPDX-FileCopyrightText: 2026 Konsole Contributors

    SPDX-License-Identifier: GPL-2.0-or-later
*/

#include "ProjectManager.h"
#include "Project.h"
#include "terminalDisplay/TerminalDisplay.h"

using namespace Konsole;

ProjectManager::ProjectManager(QObject *parent)
    : QObject(parent)
{
}

ProjectManager::~ProjectManager()
{
}

Project *ProjectManager::createProject(const QString &name)
{
    QString projectName = name;
    if (projectName.isEmpty()) {
        projectName = QStringLiteral("Project %1").arg(++_projectCounter);
    }

    auto *project = new Project(projectName, this);
    _projects.append(project);

    if (!_activeProject) {
        _activeProject = project;
    }

    Q_EMIT projectCreated(project);
    return project;
}

Project *ProjectManager::projectAt(int index) const
{
    if (index >= 0 && index < _projects.size()) {
        return _projects.at(index);
    }
    return nullptr;
}

Project *ProjectManager::projectByName(const QString &name) const
{
    for (const auto &project : _projects) {
        if (project && project->name() == name) {
            return project;
        }
    }
    return nullptr;
}

Project *ProjectManager::projectForTerminal(QObject *terminal) const
{
    for (const auto &project : _projects) {
        if (project && project->terminals().contains(qobject_cast<TerminalDisplay *>(terminal))) {
            return project;
        }
    }
    return nullptr;
}

bool ProjectManager::removeProject(Project *project)
{
    if (_projects.removeOne(project)) {
        if (_activeProject == project) {
            _activeProject = _projects.isEmpty() ? nullptr : _projects.first();
            if (_activeProject) {
                Q_EMIT activeProjectChanged(_activeProject);
            }
        }
        Q_EMIT projectRemoved(project);
        project->deleteLater();
        return true;
    }
    return false;
}

QList<QPointer<Project>> ProjectManager::projects() const
{
    return _projects;
}

int ProjectManager::projectCount() const
{
    return _projects.count();
}

Project *ProjectManager::activeProject() const
{
    return _activeProject;
}

void ProjectManager::setActiveProject(Project *project)
{
    if (_activeProject != project && _projects.contains(project)) {
        _activeProject = project;
        Q_EMIT activeProjectChanged(project);
    }
}
