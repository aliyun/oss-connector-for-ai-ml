RELEASE_VERSION = "1.0.0rc1"

PACKAGE_NAME = "osstorchconnector"
TAG_VER_LIST = [
    {
        "py": "cp38",
        "abi": "cp38",
        "platform": "manylinux_2_17_x86_64.manylinux2014_x86_64",
    },
    {
        "py": "cp39",
        "abi": "cp39",
        "platform": "manylinux_2_17_x86_64.manylinux2014_x86_64",
    },
    {
        "py": "cp310",
        "abi": "cp310",
        "platform": "manylinux_2_17_x86_64.manylinux2014_x86_64",
    },
    {
        "py": "cp311",
        "abi": "cp311",
        "platform": "manylinux_2_17_x86_64.manylinux2014_x86_64",
    },
    {
        "py": "cp312",
        "abi": "cp312",
        "platform": "manylinux_2_17_x86_64.manylinux2014_x86_64",
    },
]

UID = "aliyun"
REPO = "oss-connector-for-ai-ml"
URL_PREFIX = "https://github.com/%s/%s/releases/download/v%s/" % (UID, REPO, RELEASE_VERSION)

def get_url(name: str):
    return URL_PREFIX + name