#!/usr/bin/env python3

"""
Generate tar archive and its index

This script is designed to generate a tar archive and its corresponding index.
It can also generate an index from an existing tar archive.
Both source and target path can be specified by OSS URI or local path.

Usage:
    1. Generate tar archive and its index from source:
    python generate_tar_archive.py --endpoint <endpoint> --cred-path <cred_path> --config-path <config_path> \
                                   --tar-path <tar_path> --index-path <index_path> --source-path <source_path>
    2. Generate tar index from existing tar archive:
    python generate_tar_archive.py --endpoint <endpoint> --cred-path <cred_path> --config-path <config_path> \
                                   --tar-path <tar_path> --index-path <index_path> --index-only
"""

from osstorchconnector import generate_tar_archive
import argparse

parser = argparse.ArgumentParser(description='Generate tar archive and its index')
parser.add_argument('-ep', '--endpoint', type=str, help='Endpoint of the OSS bucket where the objects are stored.')
parser.add_argument('--cred-path', type=str, help='Credential info of the OSS bucket where the objects are stored.')
parser.add_argument('--config-path', type=str, help='Configuration file path of the OSS connector.')
parser.add_argument('--tar-path', type=str, help='Path to the tar archive. (OSS URI or local path)')
parser.add_argument('--index-path', type=str, help='Path to the tar index. (OSS URI or local path)')
parser.add_argument('--source-path', type=str, help='Path to the source directory. (OSS URI or local path)')
parser.add_argument('--index-only', action='store_true', help='''If True, generate tar index from tar archive specified by 'tar_path',
                    otherwise (by default) generate tar archive and its index from source directory specified by 'source_path'.''')


def main():
    args = parser.parse_args()
    generate_tar_archive(args.endpoint, args.cred_path, args.config_path, args.tar_path, args.index_path, args.source_path, args.index_only)


if __name__ == "__main__":
    main()
