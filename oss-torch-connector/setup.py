from setuptools import setup, find_packages
from setuptools.command.sdist import sdist as _sdist
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
import os
import time
import urllib.request
import shutil
import zipfile
from ver_tag import RELEASE_VERSION, PACKAGE_NAME, TAG_VER_LIST, get_url


WHEELS = [
    "%s-%s-%s-%s-%s.whl"
    % (
        PACKAGE_NAME,
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

                        # ====================================================
                        file_size = os.path.getsize(file_path)
                        print(f"[{whl_name}] Downloaded size: {file_size} bytes.")
                        
                        if file_size < 2048:  # 小于 2KB 极度可疑
                            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                                head_content = f.read(100)
                            print(f"!!! WARNING: File is too small. Head content: {head_content}")

                        # 照妖镜 2：验证它是不是真正的 ZIP 压缩包
                        if not zipfile.is_zipfile(file_path):
                            raise Exception(
                                f"FATAL ERROR: The downloaded file is NOT a valid WHL/ZIP file! "
                                f"It is likely an HTML/XML error page. URL: {url}"
                            )
                        # ====================================================

                        print("Whl downloaded, verified, and saved as %s" % file_path)
                        return
                    else:
                        print(
                            "Whl %s download failed and try %d times. Response.status: %d"
                            % (file_path, attempt, response.status)
                        )
            except Exception as e:
                print(
                    "Whl %s download failed and try %d times. Exception: %s"
                    % (file_path, attempt, e)
                )
            finally:
                time.sleep(2)
                
        if attempt >= ATTEMPT_TIMES:
            raise Exception("Max retries reached. %s download failed." % whl_name)


class UndefinedBDistWheelCommand(_bdist_wheel):
    def run(self):
        print("****************************************************************")
        print("Bypassing bdist_wheel build.")
        print("Pre-compiled wheels have already been downloaded in sdist phase.")
        print("****************************************************************")
        
        pass


setup(cmdclass={"sdist": CustomSDistCommand, "bdist_wheel": UndefinedBDistWheelCommand})
