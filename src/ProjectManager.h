/*
    SPDX-FileCopyrightText: 2026 Konsole Contributors

    SPDX-License-Identifier: GPL-2.0-or-later
*/

#ifndef PROJECTMANAGER_H
#define PROJECTMANAGER_H

#include <QObject>
#include <QList>
#include <QPointer>

namespace Konsole
{
class Project;

/**
 * Manages a collection of projects.
 * Ensures each project has a unique name and provides access to projects.
 */
class ProjectManager : public QObject
{
    Q_OBJECT

public:
    /**
     * Constructs a new project manager.
     */
    explicit ProjectManager(QObject *parent = nullptr);

    /**
     * Destructor.
     */
    ~ProjectManager() override;

    /**
     * Creates a new project with the given name.
     * If name is empty, generates a default name like "Project 1".
     * @param name The name of the new project
     * @return The newly created project
     */
    Project *createProject(const QString &name = QString());

    /**
     * Returns the project at the given index.
     */
    Project *projectAt(int index) const;

    /**
     * Returns the project with the given name, or nullptr if not found.
     */
    Project *projectByName(const QString &name) const;

    /**
     * Returns the project that contains the given terminal, or nullptr if not found.
     */
    Project *projectForTerminal(QObject *terminal) const;

    /**
     * Removes a project from the manager.
     * @param project The project to remove
     * @return true if the project was removed, false otherwise
     */
    bool removeProject(Project *project);

    /**
     * Returns the list of all projects.
     */
    QList<QPointer<Project>> projects() const;

    /**
     * Returns the number of projects.
     */
    int projectCount() const;

    /**
     * Returns the active/current project.
     */
    Project *activeProject() const;

    /**
     * Sets the active project.
     */
    void setActiveProject(Project *project);

Q_SIGNALS:
    /**
     * Emitted when a new project is created.
     */
    void projectCreated(Project *project);

    /**
     * Emitted when a project is removed.
     */
    void projectRemoved(Project *project);

    /**
     * Emitted when the active project changes.
     */
    void activeProjectChanged(Project *project);

private:
    QList<QPointer<Project>> _projects;
    QPointer<Project> _activeProject;
    int _projectCounter = 0;
};
}

#endif // PROJECTMANAGER_H
