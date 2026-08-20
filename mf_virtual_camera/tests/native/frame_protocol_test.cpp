#include <cassert>

#include "mfvc/frame_protocol.h"

int main() {
    using namespace mfvc::protocol;

    static_assert(nv12_frame_size(1280, 720, 1280) == 1'382'400);
    static_assert(nv12_frame_size(1279, 720, 1279) == 0);
    static_assert(nv12_frame_size(1280, 719, 1280) == 0);
    static_assert(nv12_frame_size(1280, 720, 1000) == 0);

    FrameHeader header{};
    header.magic = kMagic;
    header.version_major = kVersionMajor;
    header.version_minor = kVersionMinor;
    header.header_size = sizeof(FrameHeader);
    header.slot_count = kSlotCount;
    assert(has_valid_identity(header));

    ++header.version_major;
    assert(!has_valid_identity(header));
    return 0;
}

