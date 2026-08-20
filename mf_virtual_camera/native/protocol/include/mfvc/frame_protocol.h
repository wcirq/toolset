#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace mfvc::protocol {

inline constexpr std::array<char, 8> kMagic{'M', 'F', 'V', 'C', 'F', 'R', 'M', '1'};
inline constexpr std::uint16_t kVersionMajor = 1;
inline constexpr std::uint16_t kVersionMinor = 0;
inline constexpr std::uint32_t kSlotCount = 2;

enum class PixelFormat : std::uint32_t {
    nv12 = 0x3231564E,  // MAKEFOURCC('N', 'V', '1', '2')
};

// This structure is shared across process and language boundaries. Keep fields fixed-width,
// append new fields only, and bump the major version for incompatible changes.
struct alignas(64) FrameHeader final {
    std::array<char, 8> magic;
    std::uint16_t version_major;
    std::uint16_t version_minor;
    std::uint32_t header_size;
    std::uint32_t slot_count;
    std::uint32_t slot_size;
    std::uint32_t width;
    std::uint32_t height;
    std::uint32_t stride;
    PixelFormat pixel_format;
    std::uint32_t fps_numerator;
    std::uint32_t fps_denominator;
    std::uint64_t published_sequence;
    std::uint64_t timestamp_100ns;
    std::uint64_t writer_process_id;
    std::array<std::byte, 48> reserved;
};

static_assert(std::is_standard_layout_v<FrameHeader>);
static_assert(std::is_trivially_copyable_v<FrameHeader>);
static_assert(sizeof(FrameHeader) == 128);
static_assert(alignof(FrameHeader) == 64);

[[nodiscard]] constexpr std::size_t nv12_frame_size(
    std::uint32_t width,
    std::uint32_t height,
    std::uint32_t stride) noexcept {
    if (width == 0 || height == 0 || stride < width || (width & 1U) || (height & 1U)) {
        return 0;
    }
    return static_cast<std::size_t>(stride) * height * 3U / 2U;
}

[[nodiscard]] constexpr bool has_valid_identity(const FrameHeader& header) noexcept {
    return header.magic == kMagic && header.version_major == kVersionMajor &&
           header.header_size == sizeof(FrameHeader) && header.slot_count == kSlotCount;
}

}  // namespace mfvc::protocol

