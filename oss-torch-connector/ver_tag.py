import urllib.parse

RELEASE_VERSION = "1.2.3"

PACKAGE_NAME = "osstorchconnector"
TAG_VER_LIST = [
    {
        "py": "cp38",
        "abi": "cp38",
        "platform": "manylinux2014_x86_64.manylinux_2_17_x86_64",
    },
    {
        "py": "cp39",
        "abi": "cp39",
        "platform": "manylinux2014_x86_64.manylinux_2_17_x86_64",
    },
    {
        "py": "cp310",
        "abi": "cp310",
        "platform": "manylinux2014_x86_64.manylinux_2_17_x86_64",
    },
    {
        "py": "cp311",
        "abi": "cp311",
        "platform": "manylinux2014_x86_64.manylinux_2_17_x86_64",
    },
    {
        "py": "cp312",
        "abi": "cp312",
        "platform": "manylinux2014_x86_64.manylinux_2_17_x86_64",
    },
    {
        "py": "cp313",
        "abi": "cp313",
        "platform": "manylinux2014_x86_64.manylinux_2_17_x86_64",
    },
]

UID = "aliyun"
REPO = "oss-connector-for-ai-ml"
RELEASE_TAG_SAFE = urllib.parse.quote("%s/v%s" %(PACKAGE_NAME, RELEASE_VERSION), safe='')
URL_PREFIX = "https://github.com/%s/%s/releases/download/%s/" % (UID, REPO, RELEASE_TAG_SAFE)

# https://github.com/aliyun/oss-connector-for-ai-ml/releases/download/osstorchconnector%2Fv1.2.3/osstorchconnector-1.2.3-cp38-cp38-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
def get_url(name: str):
    return URL_PREFIX + name
