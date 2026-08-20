#include "mfvc/shared_frame_reader.h"

#include <cstring>

#include "mfvc/constants.h"
#include "mfvc/frame_protocol.h"

namespace mfvc {

SharedFrameReader::~SharedFrameReader() {
    close();
}

bool SharedFrameReader::ensure_open() noexcept {
    if (view_) {
        return true;
    }

    // Keep the named mapping fallback for isolated native tests and older senders.
    mapping_ = OpenFileMappingW(FILE_MAP_READ, FALSE, kSharedMemoryName);
    if (!mapping_) {
        HANDLE file = CreateFileW(kSharedMemoryPath, GENERIC_READ,
                                  FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                  nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file != INVALID_HANDLE_VALUE) {
            mapping_ = CreateFileMappingW(file, nullptr, PAGE_READONLY, 0, 0, nullptr);
            CloseHandle(file);
        }
    }
    if (!mapping_) {
        return false;
    }
    view_ = static_cast<const std::byte*>(MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, 0));
    if (!view_) {
        CloseHandle(mapping_);
        mapping_ = nullptr;
        return false;
    }
    return true;
}

bool SharedFrameReader::read_latest(
    void* destination,
    std::size_t destination_size,
    std::uint64_t& sequence) noexcept {
    if (!destination || !ensure_open()) {
        return false;
    }

    protocol::FrameHeader header{};
    std::memcpy(&header, view_, sizeof(header));
    if (!protocol::has_valid_identity(header) || header.pixel_format != protocol::PixelFormat::nv12 ||
        header.slot_size != destination_size || header.published_sequence == 0) {
        return false;
    }

    const auto first_sequence = header.published_sequence;
    const auto slot_index = first_sequence % protocol::kSlotCount;
    const auto slot_offset = sizeof(protocol::FrameHeader) +
                             static_cast<std::size_t>(slot_index) * header.slot_size;
    MemoryBarrier();
    std::memcpy(destination, view_ + slot_offset, destination_size);
    MemoryBarrier();

    protocol::FrameHeader confirmation{};
    std::memcpy(&confirmation, view_, sizeof(confirmation));
    if (confirmation.published_sequence != first_sequence ||
        !protocol::has_valid_identity(confirmation)) {
        return false;
    }
    sequence = first_sequence;
    return true;
}

void SharedFrameReader::close() noexcept {
    if (view_) {
        UnmapViewOfFile(view_);
        view_ = nullptr;
    }
    if (mapping_) {
        CloseHandle(mapping_);
        mapping_ = nullptr;
    }
}

}  // namespace mfvc
