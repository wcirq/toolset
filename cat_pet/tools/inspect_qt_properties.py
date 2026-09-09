"""Decode bounded Qt 5 static property metadata from the verified PE file."""
import struct
import pefile


def inspect(path, meta_rva):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    def pointer(rva):
        return struct.unpack('<Q', pe.get_data(rva, 8))[0] - base
    strings, metadata = pointer(meta_rva + 8), pointer(meta_rva + 16)
    header = struct.unpack('<14I', pe.get_data(metadata, 56))
    def string(index):
        entry = strings + index * 24
        data = pe.get_data(entry, 24)
        size, offset = struct.unpack_from('<i', data, 4)[0], struct.unpack_from('<q', data, 16)[0]
        if not 0 <= size < 256:
            raise ValueError('Invalid metadata string')
        return pe.get_data(entry + offset, size).decode('utf-8')
    print('class', string(header[1]), 'revision', header[0])
    for index in range(min(header[6], 100)):
        name, kind, flags = struct.unpack('<3I', pe.get_data(metadata + 4 * (header[7] + index * 3), 12))
        print(index, string(name), hex(kind), hex(flags))
    pe.close()


if __name__ == '__main__':
    inspect(r'C:\Program Files\Tencent\Weixin\4.1.13.12\Weixin.dll', 0x8b54db8)
