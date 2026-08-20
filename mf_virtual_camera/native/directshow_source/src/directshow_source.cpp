#include "mfvc/directshow_source.h"

#include <dvdmedia.h>
#include <ks.h>
#include <ksmedia.h>

#include <algorithm>
#include <cstring>
#include <iterator>
#include <new>

namespace mfvc {
namespace {

constexpr long kSourceWidth = 1280;
constexpr long kSourceHeight = 720;
constexpr long kFps = 30;
constexpr REFERENCE_TIME kFrameDuration = 10'000'000 / kFps;
constexpr std::size_t kSourceFrameSize = kSourceWidth * kSourceHeight * 3 / 2;
constexpr VideoMode kModes[]{{1280, 720, 1}, {640, 480, 2}};

}  // namespace

DirectShowStream::DirectShowStream(HRESULT* result, CSource* source)
    : CSourceStream(NAME("SSKJ DirectShow Video Stream"), result, source, L"Capture"),
      source_frame_(kSourceFrameSize) {
    std::fill(source_frame_.begin(), source_frame_.begin() + kSourceWidth * kSourceHeight, 16);
    std::fill(source_frame_.begin() + kSourceWidth * kSourceHeight, source_frame_.end(), 128);
}

STDMETHODIMP DirectShowStream::NonDelegatingQueryInterface(REFIID iid, void** object) {
    if (iid == IID_IAMStreamConfig) return GetInterface(static_cast<IAMStreamConfig*>(this), object);
    if (iid == IID_IKsPropertySet) return GetInterface(static_cast<IKsPropertySet*>(this), object);
    return CSourceStream::NonDelegatingQueryInterface(iid, object);
}

int DirectShowStream::mode_count() noexcept {
    return static_cast<int>(std::size(kModes));
}

const VideoMode& DirectShowStream::mode_at(int index) {
    return kModes[index];
}

HRESULT DirectShowStream::build_media_type(const VideoMode& mode, CMediaType& media_type) const {
    VIDEOINFOHEADER* video = reinterpret_cast<VIDEOINFOHEADER*>(
        media_type.AllocFormatBuffer(sizeof(VIDEOINFOHEADER)));
    if (!video) return E_OUTOFMEMORY;
    std::memset(video, 0, sizeof(*video));
    video->AvgTimePerFrame = kFrameDuration;
    video->bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    video->bmiHeader.biWidth = mode.width;
    video->bmiHeader.biHeight = mode.height;
    video->bmiHeader.biPlanes = 1;
    video->bmiHeader.biBitCount = 16;
    video->bmiHeader.biCompression = MAKEFOURCC('Y', 'U', 'Y', '2');
    video->bmiHeader.biSizeImage = mode.width * mode.height * 2;
    video->dwBitRate = video->bmiHeader.biSizeImage * 8 * kFps;
    SetRect(&video->rcSource, 0, 0, mode.width, mode.height);
    SetRect(&video->rcTarget, 0, 0, mode.width, mode.height);

    media_type.SetType(&MEDIATYPE_Video);
    media_type.SetSubtype(&MEDIASUBTYPE_YUY2);
    media_type.SetFormatType(&FORMAT_VideoInfo);
    media_type.SetTemporalCompression(FALSE);
    media_type.SetSampleSize(video->bmiHeader.biSizeImage);
    return S_OK;
}

HRESULT DirectShowStream::GetMediaType(CMediaType* media_type) {
    if (!media_type) return E_POINTER;
    return build_media_type(kModes[0], *media_type);
}

HRESULT DirectShowStream::CheckMediaType(const CMediaType* media_type) {
    if (!media_type || *media_type->Type() != MEDIATYPE_Video ||
        *media_type->Subtype() != MEDIASUBTYPE_YUY2 ||
        *media_type->FormatType() != FORMAT_VideoInfo ||
        media_type->FormatLength() < sizeof(VIDEOINFOHEADER)) {
        return E_INVALIDARG;
    }
    const auto* video = reinterpret_cast<const VIDEOINFOHEADER*>(media_type->Format());
    for (const auto& mode : kModes) {
        if (video->bmiHeader.biWidth == mode.width &&
            std::abs(video->bmiHeader.biHeight) == mode.height) return S_OK;
    }
    return VFW_E_TYPE_NOT_ACCEPTED;
}

HRESULT DirectShowStream::DecideBufferSize(IMemAllocator* allocator,
                                            ALLOCATOR_PROPERTIES* properties) {
    if (!allocator || !properties) return E_POINTER;
    const auto* video = reinterpret_cast<const VIDEOINFOHEADER*>(m_mt.Format());
    properties->cBuffers = std::max<LONG>(properties->cBuffers, 3);
    properties->cbBuffer = std::max<LONG>(properties->cbBuffer,
                                           video->bmiHeader.biSizeImage);
    ALLOCATOR_PROPERTIES actual{};
    const HRESULT result = allocator->SetProperties(properties, &actual);
    if (FAILED(result)) return result;
    return actual.cbBuffer >= properties->cbBuffer ? S_OK : E_FAIL;
}

HRESULT DirectShowStream::OnThreadCreate() {
    sample_time_ = 0;
    return S_OK;
}

void DirectShowStream::nv12_to_yuy2(const std::uint8_t* nv12, std::uint8_t* output,
                                    const VideoMode& mode) noexcept {
    const auto* y_plane = nv12;
    const auto* uv_plane = nv12 + kSourceWidth * kSourceHeight;
    for (long row = 0; row < mode.height; ++row) {
        const long source_y = row * kSourceHeight / mode.height;
        const auto* y = y_plane + source_y * kSourceWidth;
        const auto* uv = uv_plane + (source_y / 2) * kSourceWidth;
        auto* destination = output + row * mode.width * 2;
        for (long column = 0; column < mode.width; column += 2) {
            const long source_x0 = column * kSourceWidth / mode.width;
            const long source_x1 = (column + 1) * kSourceWidth / mode.width;
            const long chroma_x = source_x0 & ~1L;
            *destination++ = y[source_x0];
            *destination++ = uv[chroma_x];
            *destination++ = y[source_x1];
            *destination++ = uv[chroma_x + 1];
        }
    }
}

HRESULT DirectShowStream::FillBuffer(IMediaSample* sample) {
    if (!sample) return E_POINTER;
    BYTE* destination = nullptr;
    HRESULT result = sample->GetPointer(&destination);
    if (FAILED(result)) return result;

    const auto* video = reinterpret_cast<const VIDEOINFOHEADER*>(m_mt.Format());
    const VideoMode* selected = nullptr;
    for (const auto& mode : kModes) {
        if (video->bmiHeader.biWidth == mode.width &&
            std::abs(video->bmiHeader.biHeight) == mode.height) selected = &mode;
    }
    if (!selected) return VFW_E_TYPE_NOT_ACCEPTED;
    const long output_size = selected->width * selected->height * 2;
    if (sample->GetSize() < output_size) return E_FAIL;

    std::uint64_t sequence = 0;
    reader_.read_latest(source_frame_.data(), source_frame_.size(), sequence);
    nv12_to_yuy2(source_frame_.data(), destination, *selected);
    sample->SetActualDataLength(output_size);

    REFERENCE_TIME start = sample_time_;
    REFERENCE_TIME end = start + kFrameDuration;
    sample->SetTime(&start, &end);
    sample->SetSyncPoint(TRUE);
    sample_time_ = end;
    return S_OK;
}

STDMETHODIMP DirectShowStream::SetFormat(AM_MEDIA_TYPE* media_type) {
    if (!media_type) return E_POINTER;
    CMediaType requested(*media_type);
    const HRESULT result = CheckMediaType(&requested);
    if (FAILED(result)) return result;
    m_mt = requested;
    return S_OK;
}

STDMETHODIMP DirectShowStream::GetFormat(AM_MEDIA_TYPE** media_type) {
    if (!media_type) return E_POINTER;
    *media_type = CreateMediaType(&m_mt);
    return *media_type ? S_OK : E_OUTOFMEMORY;
}

STDMETHODIMP DirectShowStream::GetNumberOfCapabilities(int* count, int* size) {
    if (!count || !size) return E_POINTER;
    *count = mode_count();
    *size = sizeof(VIDEO_STREAM_CONFIG_CAPS);
    return S_OK;
}

STDMETHODIMP DirectShowStream::GetStreamCaps(int index, AM_MEDIA_TYPE** media_type,
                                             BYTE* capabilities) {
    if (!media_type || !capabilities) return E_POINTER;
    if (index < 0 || index >= mode_count()) return S_FALSE;
    CMediaType type;
    HRESULT result = build_media_type(mode_at(index), type);
    if (FAILED(result)) return result;
    *media_type = CreateMediaType(&type);
    if (!*media_type) return E_OUTOFMEMORY;

    auto* caps = reinterpret_cast<VIDEO_STREAM_CONFIG_CAPS*>(capabilities);
    std::memset(caps, 0, sizeof(*caps));
    caps->guid = FORMAT_VideoInfo;
    caps->VideoStandard = AnalogVideo_None;
    caps->InputSize = {kSourceWidth, kSourceHeight};
    caps->MinCroppingSize = {mode_at(index).width, mode_at(index).height};
    caps->MaxCroppingSize = caps->MinCroppingSize;
    caps->MinOutputSize = caps->MinCroppingSize;
    caps->MaxOutputSize = caps->MinCroppingSize;
    caps->MinFrameInterval = kFrameDuration;
    caps->MaxFrameInterval = kFrameDuration;
    caps->MinBitsPerSecond = mode_at(index).width * mode_at(index).height * 16 * kFps;
    caps->MaxBitsPerSecond = caps->MinBitsPerSecond;
    return S_OK;
}

STDMETHODIMP DirectShowStream::Set(REFGUID, DWORD, LPVOID, DWORD, LPVOID, DWORD) {
    return E_NOTIMPL;
}

STDMETHODIMP DirectShowStream::Get(REFGUID property_set, DWORD property_id, LPVOID, DWORD,
                                   LPVOID property_data, DWORD data_size, DWORD* returned) {
    if (property_set != AMPROPSETID_Pin || property_id != AMPROPERTY_PIN_CATEGORY) {
        return E_PROP_SET_UNSUPPORTED;
    }
    if (returned) *returned = sizeof(GUID);
    if (!property_data) return S_OK;
    if (data_size < sizeof(GUID)) return E_UNEXPECTED;
    *static_cast<GUID*>(property_data) = PIN_CATEGORY_CAPTURE;
    return S_OK;
}

STDMETHODIMP DirectShowStream::QuerySupported(REFGUID property_set, DWORD property_id,
                                              DWORD* support_type) {
    if (!support_type) return E_POINTER;
    if (property_set != AMPROPSETID_Pin || property_id != AMPROPERTY_PIN_CATEGORY) {
        return E_PROP_SET_UNSUPPORTED;
    }
    *support_type = KSPROPERTY_SUPPORT_GET;
    return S_OK;
}

CUnknown* WINAPI DirectShowSource::CreateInstance(IUnknown* outer, HRESULT* result) {
    auto* source = new (std::nothrow) DirectShowSource(outer, result);
    if (!source && result) *result = E_OUTOFMEMORY;
    return source;
}

DirectShowSource::DirectShowSource(IUnknown* outer, HRESULT* result)
    : CSource(NAME("SSKJ DirectShow Virtual Camera"), outer, kDirectShowCameraGuid) {
    auto* stream = new (std::nothrow) DirectShowStream(result, this);
    if (!stream && result) *result = E_OUTOFMEMORY;
}

}  // namespace mfvc
