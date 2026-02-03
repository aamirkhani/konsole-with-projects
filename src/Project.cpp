/*
    SPDX-FileCopyrightText: 2026 Konsole Contributors

    SPDX-License-Identifier: GPL-2.0-or-later
*/

#include "Project.h"
#include "terminalDisplay/TerminalDisplay.h"

using namespace Konsole;

int Project::_nextId = 1;

Project::Project(const QString &name, QObject *parent)
    : QObject(parent)
    , _name(name)
    , _id(_nextId++)
{
}

QString Project::name() const
{
    return _name;
}

void Project::setName(const QString &name)
{
    if (_name != name) {
        _name = name;
        Q_EMIT nameChanged(name);
    }
}

int Project::id() const
{
    return _id;
}

void Project::addTerminal(TerminalDisplay *terminal)
{
    if (terminal && !_terminals.contains(terminal)) {
        _terminals.append(terminal);
        Q_EMIT terminalAdded(terminal);
    }
}

void Project::removeTerminal(TerminalDisplay *terminal)
{
    if (_terminals.removeOne(terminal)) {
        Q_EMIT terminalRemoved(terminal);
    }
}

QList<QPointer<TerminalDisplay>> Project::terminals() const
{
    return _terminals;
}

int Project::terminalCount() const
{
    return _terminals.count();
}
