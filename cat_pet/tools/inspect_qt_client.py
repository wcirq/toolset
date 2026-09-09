"""Static Qt adaptation evidence; never loads target DLLs or calls addresses."""
import argparse
import hashlib
import json
import re
from pathlib import Path

import pefile


def inspect(path):
    data = path.read_bytes()
    pe = pefile.PE(data=data, fast_load=True)
    pe.parse_data_directories(directories=[0, 1, 6])
    exports = [s.name.decode('ascii', 'replace') for s in
               getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', []) if s.name]
    def location(offset):
        return {'offset': hex(offset), 'rva': hex(pe.get_rva_from_offset(offset))}
    clues = []
    for token in (b'QApplication', b'QWidget', b'QAbstractItemView', b'QListView',
                  b'QAbstractItemModel', b'session_list', b'session_item_',
                  b'chat_message_list', b'chat_bubble_item_view', b'chat_input_field',
                  b'QAccessible', b'QT_ACCESSIBILITY'):
        offsets = [m.start() for m in re.finditer(re.escape(token), data)]
        clues.append({'token': token.decode(), 'count': len(offsets),
                      'locations': [location(o) for o in offsets[:12]]})
    classes = sorted(set(m.group().decode('ascii', 'replace') for m in
                         re.finditer(rb'\.\?AV[^\x00\r\n]{1,180}@@\x00', data)
                         if re.search(rb'(Session|session|QListView|QAbstractItem|QWidget)', m.group())))
    targets = {int(loc['rva'], 16): clue['token'] for clue in clues
               if clue['token'] in ('session_list', 'session_item_', 'chat_message_list',
                                    'chat_bubble_item_view', 'chat_input_field') for loc in clue['locations']}
    references = []
    import struct
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        raw = section.get_data()
        # Candidate RIP-relative LEA/MOV only; instruction boundaries require
        # independent disassembly, so these are not accepted function entries.
        for match in re.finditer(rb'[\x48-\x4f][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', raw):
            offset = match.start()
            if offset + 7 > len(raw):
                continue
            rva = section.VirtualAddress + offset
            destination = rva + 7 + struct.unpack_from('<i', raw, offset + 3)[0]
            if destination in targets:
                references.append({'instruction_rva_candidate': hex(rva),
                                   'string': targets[destination], 'string_rva': hex(destination)})
    result = {'file': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
              'qt_exports': [s for s in exports if any(k in s for k in
                              ('QApplication', 'QWidget', 'QAbstractItem', 'QAccessible', 'QListView'))],
              'clues': clues, 'rtti_classes': classes[:100], 'reference_candidates': references,
              'note': 'String RVAs are data locations, not callable function addresses.'}
    pe.close()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('binary', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.binary)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2))
