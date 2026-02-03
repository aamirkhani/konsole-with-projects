/*
    SPDX-FileCopyrightText: 2026 Konsole Contributors

    SPDX-License-Identifier: GPL-2.0-or-later
*/

#ifndef PROJECTHEADERWIDGET_H
#define PROJECTHEADERWIDGET_H

#include <QWidget>
#include <QComboBox>
#include <QPushButton>
#include <QLabel>

namespace Konsole
{
class ProjectManager;
class Project;

/**
 * A widget that displays and manages projects in the UI.
 * Shows the current project and allows switching between projects.
 */
class ProjectHeaderWidget : public QWidget
{
    Q_OBJECT

public:
    /**
     * Constructs a new project header widget.
     */
    explicit ProjectHeaderWidget(ProjectManager *manager, QWidget *parent = nullptr);

    /**
     * Refresh the project list display.
     */
    void refreshProjects();

    /**
     * Update to show current project.
     */
    void updateCurrentProject();

Q_SIGNALS:
    /**
     * Emitted when user selects a different project.
     */
    void projectSelected(Project *project);

private Q_SLOTS:
    void onProjectComboChanged(int index);
    void onNewProjectClicked();
    void onProjectCreated(Project *project);
    void onProjectRemoved(Project *project);
    void onActiveProjectChanged(Project *project);

private:
    void setupUI();

    ProjectManager *_projectManager = nullptr;
    QComboBox *_projectCombo = nullptr;
    QPushButton *_newProjectButton = nullptr;
    QLabel *_projectLabel = nullptr;
};

}

#endif // PROJECTHEADERWIDGET_H
