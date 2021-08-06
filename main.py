import sys
import os

parent_folder_path = os.path.abspath(os.path.dirname(__file__))
sys.path.append(parent_folder_path)

from plugin.plexy import Plexy

if __name__ == '__main__':
    Plexy()