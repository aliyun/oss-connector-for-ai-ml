RELEASE_VERSION = "1.0.0rc1"

PACKAGE_NAME = "osstorchconnector"
TAG_VER_LIST = [
    {
        "py": "cp38",
        "abi": "cp38",
        "platform": "manylinux",
    },
    {
        "py": "cp39",
        "abi": "cp39",
        "platform": "manylinux",
    },
    {
        "py": "cp310",
        "abi": "cp310",
        "platform": "manylinux",
    },
    {
        "py": "cp311",
        "abi": "cp311",
        "platform": "manylinux",
    },
    {
        "py": "cp312",
        "abi": "cp312",
        "platform": "manylinux",
    },
]


URL_PREFIX = "https://github.com/aliyun/oss-connector-for-ai-ml/releases/download/v%s/" % RELEASE_VERSION

def get_url(name: str):
    return URL_PREFIX + name
