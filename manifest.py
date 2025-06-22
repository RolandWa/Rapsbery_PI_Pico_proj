# This manifest.py should be in micropythonportsrp2

# Include standard modules for the board
include($(MPY_DIR)portsrp2modulesmicropython.py)

# Include your custom application modules from your folder
# 'my_app_modules' should be relative to the 'portsrp2' directory
# This recursively includes all .py files in 'my_app_modules'
# The 'package' directive is good for including a directory as a Python package.
# Alternatively, use 'module(my_app_modulesmy_file.py)' for individual files.
package(my_app_modules)