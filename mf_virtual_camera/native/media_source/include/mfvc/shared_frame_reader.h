#pragma once

#include <Windows.h>

#include <cstddef>
#include <cstdint>

namespace mfvc {

class SharedFrameReader final {
public:
    SharedFrameReader() noexcept = default;
    ~SharedFrameReader();

    SharedFrameReader(const SharedFrameReader&) = delete;
    SharedFrameReader& operator=(const SharedFrameReader&) = delete;

    bool read_latest(void* destination, std::size_t destination_size, std::uint64_t& sequence) noexcept;
    void close() noexcept;

private:
    bool ensure_open() noexcept;

    HANDLE mapping_ = nullptr;
    const std::byte* view_ = nullptr;
};

}  // namespace mfvc

