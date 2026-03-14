#!/usr/bin/env python3
"""Linux PowerToys entry point."""

import sys
import os


def main():
    # Ensure gi uses GTK 3
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    from .app import PowerToysApp
    app = PowerToysApp()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
