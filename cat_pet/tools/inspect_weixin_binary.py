"""Static metadata only: never loads or calls client code."""
import argparse
import hashlib
import json
from pathlib import Path
import pefile


def inspect(path):
    pe = pefile.PE(str(path), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT'],
                                          pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    exports = [{'name': entry.name.decode('utf-8', 'replace') if entry.name else '#'+str(entry.ordinal),
                'rva': hex(entry.address)} for entry in getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', [])]
    imports = [entry.dll.decode('ascii', 'replace') for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', [])]
    result = {'file': path.name, 'bytes': path.stat().st_size, 'sha256': hashlib.file_digest(path.open('rb'), 'sha256').hexdigest(),
              'machine': hex(pe.FILE_HEADER.Machine), 'image_base': hex(pe.OPTIONAL_HEADER.ImageBase),
              'exports': exports, 'imports': imports}
    pe.close()
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    names = ['Weixin.dll', 'ilink2.dll', 'ilink_wrapper.dll', 'wxpublic.dll', 'WeixinExt.exe']
    results = [inspect(args.directory / name) for name in names if (args.directory / name).exists()]
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in results:
        candidates = [e['name'] for e in item['exports'] if any(k in e['name'].lower() for k in ('send','recv','message','callback','session','init'))]
        print(item['file'], 'exports=',len(item['exports']), 'candidates=',candidates[:40])
