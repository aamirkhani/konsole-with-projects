/*
    SPDX-FileCopyrightText: 2026 Konsole Contributors

    SPDX-License-Identifier: GPL-2.0-or-later
*/

#include "ProjectHeaderWidget.h"
#include "Project.h"
#include "ProjectManager.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>

using namespace Konsole;

ProjectHeaderWidget::ProjectHeaderWidget(ProjectManager *manager, QWidget *parent)
    : QWidget(parent)
    , _projectManager(manager)
{
    setupUI();
    
    if (_projectManager) {
        connect(_projectManager, &ProjectManager::projectCreated, this, &ProjectHeaderWidget::onProjectCreated);
        connect(_projectManager, &ProjectManager::projectRemoved, this, &ProjectHeaderWidget::onProjectRemoved);
        connect(_projectManager, &ProjectManager::activeProjectChanged, this, &ProjectHeaderWidget::onActiveProjectChanged);
    }
    
    refreshProjects();
}

void ProjectHeaderWidget::setupUI()
{
    auto layout = new QHBoxLayout(this);
    layout->setContentsMargins(5, 2, 5, 2);
    layout->setSpacing(5);
    
    _projectLabel = new QLabel(QStringLiteral("Project:"));
    layout->addWidget(_projectLabel);
    
    _projectCombo = new QComboBox();
    _projectCombo->setMinimumWidth(150);
    layout->addWidget(_projectCombo);
    connect(_projectCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &ProjectHeaderWidget::onProjectComboChanged);
    
    _newProjectButton = new QPushButton(QStringLiteral("+"));
    _newProjectButton->setMaximumWidth(40);
    _newProjectButton->setToolTip(QStringLiteral("Create new project"));
    layout->addWidget(_newProjectButton);
    connect(_newProjectButton, &QPushButton::clicked, this, &ProjectHeaderWidget::onNewProjectClicked);
    
    layout->addStretch();
    
    setMaximumHeight(35);
}

void ProjectHeaderWidget::refreshProjects()
{
    if (!_projectManager) {
        return;
    }
    
    _projectCombo->blockSignals(true);
    _projectCombo->clear();
    
    int currentIndex = 0;
    int activeIndex = 0;
    Project *activeProject = _projectManager->activeProject();
    
    for (int i = 0; i < _projectManager->projectCount(); ++i) {
        Project *proj = _projectManager->projectAt(i);
        if (proj) {
            _projectCombo->addItem(proj->name(), QVariant::fromValue(static_cast<void*>(proj)));
            if (proj == activeProject) {
                activeIndex = i;
            }
        }
    }
    
    _projectCombo->setCurrentIndex(activeIndex);
    _projectCombo->blockSignals(false);
}

void ProjectHeaderWidget::updateCurrentProject()
{
    if (!_projectManager) {
        return;
    }
    
    Project *active = _projectManager->activeProject();
    for (int i = 0; i < _projectCombo->count(); ++i) {
        if (static_cast<Project*>(_projectCombo->itemData(i, Qt::UserRole).value<void*>()) == active) {
            _projectCombo->setCurrentIndex(i);
            break;
        }
    }
}

void ProjectHeaderWidget::onProjectComboChanged(int index)
{
    if (!_projectManager || index < 0) {
        return;
    }
    
    Project *proj = _projectManager->projectAt(index);
    if (proj) {
        _projectManager->setActiveProject(proj);
        Q_EMIT projectSelected(proj);
    }
}

void ProjectHeaderWidget::onNewProjectClicked()
{
    if (!_projectManager) {
        return;
    }
    
    Project *newProj = _projectManager->createProject();
    refreshProjects();
    updateCurrentProject();
}

void ProjectHeaderWidget::onProjectCreated(Project *project)
{
    refreshProjects();
}

void ProjectHeaderWidget::onProjectRemoved(Project *project)
{
    refreshProjects();
}

void ProjectHeaderWidget::onActiveProjectChanged(Project *project)
{
    updateCurrentProject();
}
