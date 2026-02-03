/*
    SPDX-FileCopyrightText: 2026 Konsole Contributors

    SPDX-License-Identifier: GPL-2.0-or-later
*/

#ifndef PROJECT_H
#define PROJECT_H

#include <QObject>
#include <QString>
#include <QList>
#include <QPointer>

namespace Konsole
{
class TerminalDisplay;

/**
 * Represents a project which contains one or more terminal tabs.
 * Projects provide a hierarchical organization level above tabs.
 */
class Project : public QObject
{
    Q_OBJECT

public:
    /**
     * Constructs a new project with the given name.
     * @param name The display name of the project
     * @param parent The parent object
     */
    explicit Project(const QString &name = QString(), QObject *parent = nullptr);

    /**
     * Returns the name of the project.
     */
    QString name() const;

    /**
     * Sets the name of the project.
     */
    void setName(const QString &name);

    /**
     * Returns the unique ID of the project.
     */
    int id() const;

    /**
     * Adds a terminal display to this project.
     */
    void addTerminal(TerminalDisplay *terminal);

    /**
     * Removes a terminal display from this project.
     */
    void removeTerminal(TerminalDisplay *terminal);

    /**
     * Returns the list of terminals in this project.
     */
    QList<QPointer<TerminalDisplay>> terminals() const;

    /**
     * Returns the number of terminals in this project.
     */
    int terminalCount() const;

Q_SIGNALS:
    /**
     * Emitted when the project name changes.
     */
    void nameChanged(const QString &name);

    /**
     * Emitted when a terminal is added to the project.
     */
    void terminalAdded(TerminalDisplay *terminal);

    /**
     * Emitted when a terminal is removed from the project.
     */
    void terminalRemoved(TerminalDisplay *terminal);

private:
    QString _name;
    int _id;
    QList<QPointer<TerminalDisplay>> _terminals;

    static int _nextId;
};
}

#endif // PROJECT_H
