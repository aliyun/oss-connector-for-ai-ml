from setuptools import setup, find_packages
from setuptools.command.sdist import sdist as _sdist
from setuptools.command.bdist_wheel import bdist_wheel as _bdist_wheel
import os
import time
import urllib.request
import shutil
from ver_tag import RELEASE_VERSION, PACKGE_NAME, TAG_VER_LIST, get_url


WHEELS = [
    "%s-%s-%s-%s-%s.whl"
    % (
        PACKGE_NAME,
        RELEASE_VERSION,
        tag_ver["py"],
        tag_ver["abi"],
        tag_ver["platform"],
    )
    for tag_ver in TAG_VER_LIST
]

DIST_DIR = "dist/"
DIST_DIR_TMP = "tmp.dist/"
ATTEMPT_TIMES = 3

class CustomSDistCommand(_sdist):
    def run(self):
        if os.path.exists(DIST_DIR):
            if os.listdir(DIST_DIR):
                raise Exception(
                    f"The directory '{DIST_DIR}' already exists and is not empty."
                )
            else:
                print(f"Directory '{DIST_DIR}' exists.")
        else:
            os.makedirs(DIST_DIR)
            print(f"Directory '{DIST_DIR}' created successfully.")

        os.makedirs(DIST_DIR_TMP, exist_ok=True)

        # download to tmp
        for name in WHEELS:
            url = get_url(name)
            self.download_whl(name, url, DIST_DIR_TMP)

        # move whl from tmp to dist
        for name in WHEELS:
            source_file = os.path.join(DIST_DIR_TMP, name)
            destination_file = os.path.join(DIST_DIR, name)

            if os.path.isfile(source_file) and name.endswith(".whl"):
                shutil.move(source_file, destination_file)
                print(f"Moved: {source_file} -> {destination_file}")

    def download_whl(self, whl_name, url, dir):
        attempt = 0
        file_path = os.path.join(dir, whl_name)
        while attempt < ATTEMPT_TIMES:
            attempt += 1
            try:
                with urllib.request.urlopen(url) as response:
                    if response.status == 200:
                        with open(file_path, "wb") as file:
                            file.write(response.read())

                        print("Whl downloaded and saved as %s" % file_path)
                        return
                    else:
                        print(
                            "Whl %s download failed and try %d times. Response.status: %d"
                            % (file_path, attempt, response.status_code)
                        )
            except Exception as e:
                print(
                    "Whl %s download failed and try %d times. Exception: %s"
                    % (file_path, attempt, e)
                )
            finally:
                time.sleep(2)
        if attempt >= ATTEMPT_TIMES:
            # print("Max retries reached. %s download failed." % whl_name)
            raise Exception("Max retries reached. %s download failed." % whl_name)


class UndefinedBDistWheelCommand(_bdist_wheel):
    def run(self):
        raise Exception(
            "bdist_wheel is undefined as it is overriden by UndefinedBDistWheelCommand"
        )


setup(cmdclass={"sdist": CustomSDistCommand, "bdist_wheel": UndefinedBDistWheelCommand})

