"""Fetch the pinned, unmodified FFmpeg player and its upstream notices."""
import hashlib
from pathlib import Path
import urllib.request
import zipfile

VERSION = '9.0.2'
URL = 'https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip'
SHA256 = '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
ROOT = Path(__file__).resolve().parents[1]


def main():
    archive = ROOT / 'build' / 'ffmpeg-essentials.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        urllib.request.urlretrieve(URL, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError('FFmpeg archive SHA-256 mismatch')
    target = ROOT / 'vendor' / 'ffmpeg'
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            relative = Path(*Path(name).parts[1:])
            if not relative.parts or relative.is_absolute() or '..' in relative.parts:
                continue
            if str(relative).replace('\\', '/') not in ('bin/ffplay.exe', 'LICENSE', 'README.txt'):
                continue
            dest = target / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(name))
    if not (target / 'bin' / 'ffplay.exe').is_file() or not (target / 'LICENSE').is_file():
        raise RuntimeError('FFmpeg player or license missing')
    (target / 'SOURCE.txt').write_text(
        'Unmodified ffplay from FFmpeg ' + VERSION + ' essentials by Gyan Doshi.\n'
        'Distributed as a separate executable under GPLv3. See LICENSE and README.txt.\n'
        'Binary archive (SHA-256 verified): ' + URL + '\n'
        'Upstream source and build/library configuration: https://www.gyan.dev/ffmpeg/builds/\n'
        'FFmpeg source revision: https://github.com/FFmpeg/FFmpeg/commit/946fcce07b\n'
        'Build archive and source information: https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2\n',
        encoding='utf-8')
    print('ffplay ' + VERSION + ' bundled and verified')


if __name__ == '__main__':
    main()
