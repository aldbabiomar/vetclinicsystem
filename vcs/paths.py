"""Where things are on disk.

ROOT is the install's own folder -- the checkout, or a release folder the
in-app updater unpacked -- which holds VERSION, installer_assets/, the
launchers, and (without a data dir) uploads/ and logs/. Modules find it here
rather than from their own __file__, which since the move into the vcs/
package is one or two folders deeper than it used to be."""
import os

PACKAGE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PACKAGE)
