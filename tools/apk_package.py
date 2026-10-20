"""Add classes*.dex and native libraries to the aapt2-linked base APK.

Usage: python -I tools/apk_package.py base.apk out.apk dex_dir staging_dir
staging_dir contains lib/<abi>/*.so; everything under it is added with its relative path.
"""
import os
import sys
import zipfile


def main(base, out, dex_dir, staging):
    with zipfile.ZipFile(base) as src, zipfile.ZipFile(out, 'w') as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            zi = zipfile.ZipInfo(info.filename, date_time=(1981, 1, 1, 1, 1, 2))
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            dst.writestr(zi, data)
        for name in sorted(os.listdir(dex_dir)):
            if name.endswith('.dex'):
                zi = zipfile.ZipInfo(name, date_time=(1981, 1, 1, 1, 1, 2))
                zi.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(zi, open(os.path.join(dex_dir, name), 'rb').read())
        for root, _, files in os.walk(staging):
            for f in sorted(files):
                path = os.path.join(root, f)
                rel = os.path.relpath(path, staging).replace(os.sep, '/')
                zi = zipfile.ZipInfo(rel, date_time=(1981, 1, 1, 1, 1, 2))
                zi.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(zi, open(path, 'rb').read())


if __name__ == '__main__':
    main(*sys.argv[1:5])
