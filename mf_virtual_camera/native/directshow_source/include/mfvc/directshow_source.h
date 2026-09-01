#pragma once

#include <streams.h>

#include <cstdint>
#include <vector>

#include "mfvc/shared_frame_reader.h"

namespace mfvc {

inline constexpr GUID kDirectShowCameraGuid{
    0x3f0c8ec8, 0xd587, 0x43b7, {0xa2, 0x9b, 0xb4, 0x10, 0x6b, 0x91, 0xe4, 0x31}};

struct VideoMode final {
    long width;
    long height;
    long source_step;
};

class DirectShowStream final : public CSourceStream, public IAMStreamConfig, public IKsPropertySet {
public:
    DirectShowStream(HRESULT* result, CSource* source);

    DECLARE_IUNKNOWN;
    STDMETHODIMP NonDelegatingQueryInterface(REFIID iid, void** object) override;
    HRESULT CheckMediaType(const CMediaType* media_type) override;
    HRESULT GetMediaType(CMediaType* media_type) override;
    HRESULT DecideBufferSize(IMemAllocator* allocator, ALLOCATOR_PROPERTIES* properties) override;
    HRESULT FillBuffer(IMediaSample* sample) override;
    HRESULT OnThreadCreate() override;

    STDMETHODIMP SetFormat(AM_MEDIA_TYPE* media_type) override;
    STDMETHODIMP GetFormat(AM_MEDIA_TYPE** media_type) override;
    STDMETHODIMP GetNumberOfCapabilities(int* count, int* size) override;
    STDMETHODIMP GetStreamCaps(int index, AM_MEDIA_TYPE** media_type, BYTE* capabilities) override;

    STDMETHODIMP Set(REFGUID property_set, DWORD property_id, LPVOID instance_data,
                     DWORD instance_size, LPVOID property_data, DWORD data_size) override;
    STDMETHODIMP Get(REFGUID property_set, DWORD property_id, LPVOID instance_data,
                     DWORD instance_size, LPVOID property_data, DWORD data_size,
                     DWORD* returned) override;
    STDMETHODIMP QuerySupported(REFGUID property_set, DWORD property_id,
                                DWORD* support_type) override;

private:
    HRESULT build_media_type(const VideoMode& mode, CMediaType& media_type) const;
    static const VideoMode& mode_at(int index);
    static int mode_count() noexcept;
    static void nv12_to_yuy2(const std::uint8_t* nv12, std::uint8_t* yuy2,
                             const VideoMode& mode) noexcept;

    SharedFrameReader reader_;
    std::vector<std::uint8_t> source_frame_;
    REFERENCE_TIME sample_time_ = 0;
    std::uint64_t last_sequence_ = 0;
    ULONGLONG last_fresh_tick_ = 0;
};

class DirectShowSource final : public CSource {
public:
    static CUnknown* WINAPI CreateInstance(IUnknown* outer, HRESULT* result);

private:
    DirectShowSource(IUnknown* outer, HRESULT* result);
};

}  // namespace mfvc
