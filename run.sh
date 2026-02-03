#!/bin/bash
# Run konsole-projects with bundled libraries
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LD_LIBRARY_PATH="$DIR:$LD_LIBRARY_PATH"
exec "$DIR/konsole-projects" "$@"
