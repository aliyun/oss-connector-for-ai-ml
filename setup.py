from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import os
import subprocess
import shutil


class BuildExtension(Extension):
    def __init__(self, name, source_dir=''):
        Extension.__init__(self, name, sources=[source_dir])
        self.source_dir = os.path.abspath(source_dir)

class LibraryBuild(build_ext):
    user_options = build_ext.user_options + [
        ('library-path=', None, 'oss_connector library path'),
    ]
    def initialize_options(self):
        super().initialize_options()
        self.library_path = None
    def run(self):
        if not self.library_path:
            raise RuntimeError("library path is not specified by '--library-path'")
        self.library_path = os.path.abspath(self.library_path)
        if os.path.exists(self.library_path):
            print('library path:', self.library_path)
        else:
            raise RuntimeError("invalid library path: " + self.library_path)
        for ext in self.extensions:
            self.build_extension(ext)

    def run_command(self, command, cwd):
        try:
            subprocess.run(command, capture_output=True, text=True, check=True, cwd=cwd)
        except subprocess.CalledProcessError as e:
            print(f"Command '{' '.join(command)}' failed with exit code {e.returncode}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            raise RuntimeError("Subprocess execution failed") from e

    def build_extension(self, ext):
        print('name:', ext.name)
        print('source path:', ext.source_dir)
        print('current dir:', os.getcwd())

        # copy .so
        library_file_name = os.path.basename(self.library_path)
        dest_so_path = os.path.abspath(
            os.path.join(self.build_lib, 'osstorchconnector', '_oss_connector', library_file_name))
        print('copy %s to %s' % (self.library_path, dest_so_path))
        shutil.copy(self.library_path, dest_so_path)


setup(
    ext_modules=[BuildExtension('oss_connector', '.')],
    cmdclass=dict(build_ext=LibraryBuild),
)
