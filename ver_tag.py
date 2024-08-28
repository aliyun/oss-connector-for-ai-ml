RELEASE_VERSION = "1.0.0rc1"

PACKAGE_NAME = "osstorchconnector"
TAG_VER_LIST = [
    {
        "py": "cp38",
        "abi": "cp38",
        "platform": "linux_x86_64",
    },
    {
        "py": "cp39",
        "abi": "cp39",
        "platform": "linux_x86_64",
    },
    {
        "py": "cp310",
        "abi": "cp310",
        "platform": "linux_x86_64",
    },
    {
        "py": "cp311",
        "abi": "cp311",
        "platform": "linux_x86_64",
    },
    {
        "py": "cp312",
        "abi": "cp312",
        "platform": "linux_x86_64",
    },
]


URL_PREFIX = "https://github.com/aliyun/oss-connector-for-ai-ml/releases/download/v%s/" % RELEASE_VERSION

def get_url(name: str):
    return URL_PREFIX + name
