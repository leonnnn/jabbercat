#!/usr/bin/env python3
import asyncio
import logging
import os.path
import pathlib
import subprocess
import sys

os.environ["QUAMASH_QTIMPL"] = "PyQt5"

import jabbercat.Qt as Qt  # NOQA
import quamash


def get_git_version(path: pathlib.Path):
    if not (path / ".git").is_dir():
        return

    try:
        commit_id = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(path),
        )
    except subprocess.CalledProcessError:
        return

    commit_id = commit_id.decode().strip()[:7]
    return commit_id


def format_dep_version(name, pkg, version=None):
    print(
        "{}: {} (git: {}), {}".format(
            name,
            getattr(pkg, "__version__", version),
            get_git_version(pathlib.Path(pkg.__path__[0]).parent) or "N/A",
            pkg.__path__,
        )
    )


def print_version():
    import platform
    import sys

    import PyQt5

    print("Platform: {}".format(platform.platform()))
    print("Python: {}".format(sys.version))

    print(
        "PyQt5: {} (Qt: {}), ".format(
            Qt.PYQT_VERSION_STR,
            Qt.QT_VERSION_STR,
            PyQt5.__path__,
        )
    )

    format_dep_version("Quamash", quamash)

    import aiosasl

    format_dep_version("aiosasl", aiosasl)

    import aioopenssl

    format_dep_version("aioopenssl", aioopenssl)

    import aioxmpp

    format_dep_version("aioxmpp", aioxmpp)

    import sqlalchemy

    format_dep_version("sqlalchemy", sqlalchemy)

    import jclib

    format_dep_version("jclib", jclib)

    import jabbercat
    import jabbercat.version as jc_version

    format_dep_version("jabbercat", jabbercat, jc_version.version)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-V", "--version",
        action="store_true",
        default=False,
        help="Show version information and exit."
    )

    args = parser.parse_args()

    if args.version:
        print_version()
        sys.exit(0)

    app = Qt.QApplication(sys.argv)

    Qt.QResource.registerResource("resources.rcc")

    icon = Qt.QIcon()
    icon.addFile(":/icons/16x16/trayicon.png")
    icon.addFile(":/icons/24x24/trayicon.png")
    icon.addFile(":/icons/32x32/trayicon.png")

    app.setApplicationName("jabbercat")
    app.setApplicationDisplayName("JabberCat")
    app.setWindowIcon(icon)
    app.setQuitOnLastWindowClosed(False)

    import jabbercat.main

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)-15s %(levelname)s:%(name)s: %(message)s"
    )
    logging.getLogger("quamash").setLevel(logging.INFO)
    logging.getLogger("aioxmpp").setLevel(logging.DEBUG)
    logging.getLogger("aioxmpp.XMLStream").setLevel(logging.DEBUG)

    locale = Qt.QLocale.system().name()
    qttr = Qt.QTranslator(parent=app)
    if not qttr.load("qt_" + locale,
                     Qt.QLibraryInfo.location(
                         Qt.QLibraryInfo.TranslationsPath)):
        logging.warning("failed to load Qt translations for %s", locale)
    else:
        app.installTranslator(qttr)

    qttr = Qt.QTranslator(parent=app)
    if not qttr.load("qttranslations/jabbercat_" + locale):
        logging.warning("failed to load JabberCat translations for %s", locale)
    else:
        app.installTranslator(qttr)

    asyncio.set_event_loop(quamash.QEventLoop(app=app))
    loop = asyncio.get_event_loop()
    main = jabbercat.main.QtMain(loop)
    try:
        returncode = loop.run_until_complete(main.run())
    finally:
        loop.close()
        # try very hard to evict parts from memory
        import gc
        gc.collect()
        del main
        gc.collect()
        del app
        asyncio.set_event_loop(None)
        del loop
        gc.collect()

    sys.exit(returncode)

main()
