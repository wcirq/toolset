#include "mfvc/media_source.h"

#include <mferror.h>
#include <ks.h>
#include <ksmedia.h>

#include <algorithm>
#include <cstring>
#include <vector>

namespace mfvc {
namespace {

constexpr DWORD kStreamId = 0;
constexpr UINT32 kWidth = 1280;
constexpr UINT32 kHeight = 720;
constexpr UINT32 kFps = 30;
constexpr DWORD kFrameSize = kWidth * kHeight * 3 / 2;
constexpr LONGLONG kFrameDuration = 10'000'000 / kFps;
HRESULT check_pointer(const void* pointer) noexcept {
    return pointer ? S_OK : E_POINTER;
}

}  // namespace

HRESULT MediaStream::initialize(MediaSource* source, IMFStreamDescriptor* descriptor) noexcept {
    if (!source || !descriptor) return E_POINTER;
    HRESULT result = MFCreateEventQueue(events_.put());
    if (FAILED(result)) return result;
    source_.copy_from(source);
    descriptor_.copy_from(descriptor);
    return S_OK;
}

HRESULT MediaStream::GetEvent(DWORD flags, IMFMediaEvent** event) noexcept {
    return events_ ? events_->GetEvent(flags, event) : MF_E_SHUTDOWN;
}
HRESULT MediaStream::BeginGetEvent(IMFAsyncCallback* callback, IUnknown* state) noexcept {
    return events_ ? events_->BeginGetEvent(callback, state) : MF_E_SHUTDOWN;
}
HRESULT MediaStream::EndGetEvent(IMFAsyncResult* result, IMFMediaEvent** event) noexcept {
    return events_ ? events_->EndGetEvent(result, event) : MF_E_SHUTDOWN;
}
HRESULT MediaStream::QueueEvent(MediaEventType type, REFGUID extended_type, HRESULT status,
                                const PROPVARIANT* value) noexcept {
    return events_ ? events_->QueueEventParamVar(type, extended_type, status, value) : MF_E_SHUTDOWN;
}
HRESULT MediaStream::GetMediaSource(IMFMediaSource** source) noexcept {
    if (!source) return E_POINTER;
    *source = nullptr;
    std::unique_lock lock(mutex_);
    if (shutdown_ || !source_) return MF_E_SHUTDOWN;
    return source_->QueryInterface(IID_PPV_ARGS(source));
}
HRESULT MediaStream::GetStreamDescriptor(IMFStreamDescriptor** descriptor) noexcept {
    if (!descriptor) return E_POINTER;
    *descriptor = nullptr;
    std::scoped_lock lock(mutex_);
    if (shutdown_ || !descriptor_) return MF_E_SHUTDOWN;
    descriptor_->AddRef();
    *descriptor = descriptor_.get();
    return S_OK;
}
HRESULT MediaStream::RequestSample(IUnknown* token) noexcept {
    std::unique_lock lock(mutex_);
    if (shutdown_) return MF_E_SHUTDOWN;
    // Frame Server can request its first sample while IMFMediaStream2 is still
    // completing the RUNNING transition. The source Start path already gates
    // publication of this stream, so accepting that request avoids losing it.

    winrt::com_ptr<IMFSample> sample;
    winrt::com_ptr<IMFMediaBuffer> buffer;
    HRESULT result = allocator_ ? allocator_->AllocateSample(sample.put()) : MFCreateSample(sample.put());
    if (FAILED(result)) return result;
    if (allocator_) {
        result = sample->GetBufferByIndex(0, buffer.put());
    } else {
        result = MFCreateMemoryBuffer(kFrameSize, buffer.put());
        if (SUCCEEDED(result)) result = sample->AddBuffer(buffer.get());
    }
    if (FAILED(result)) return result;

    std::vector<BYTE> frame(kFrameSize);
    std::memset(frame.data(), 16, kWidth * kHeight);
    std::memset(frame.data() + kWidth * kHeight, 128, kFrameSize - kWidth * kHeight);
    std::uint64_t sequence = last_sequence_;
    reader_.read_latest(frame.data(), kFrameSize, sequence);
    last_sequence_ = sequence;

    winrt::com_ptr<IMF2DBuffer2> buffer2d;
    if (SUCCEEDED(buffer->QueryInterface(IID_PPV_ARGS(buffer2d.put())))) {
        BYTE* scanline = nullptr;
        BYTE* buffer_start = nullptr;
        LONG pitch = 0;
        DWORD length = 0;
        result = buffer2d->Lock2DSize(MF2DBuffer_LockFlags_Write, &scanline, &pitch,
                                      &buffer_start, &length);
        if (FAILED(result)) return result;
        for (UINT32 row = 0; row < kHeight; ++row) {
            std::memcpy(scanline + static_cast<std::ptrdiff_t>(row) * pitch,
                        frame.data() + row * kWidth, kWidth);
        }
        BYTE* uv = scanline + static_cast<std::ptrdiff_t>(kHeight) * pitch;
        for (UINT32 row = 0; row < kHeight / 2; ++row) {
            std::memcpy(uv + static_cast<std::ptrdiff_t>(row) * pitch,
                        frame.data() + kWidth * kHeight + row * kWidth, kWidth);
        }
        buffer2d->Unlock2D();
    } else {
        BYTE* bytes = nullptr;
        DWORD maximum = 0;
        result = buffer->Lock(&bytes, &maximum, nullptr);
        if (FAILED(result)) return result;
        std::memcpy(bytes, frame.data(), std::min<DWORD>(maximum, kFrameSize));
        buffer->Unlock();
        result = buffer->SetCurrentLength(kFrameSize);
        if (FAILED(result)) return result;
    }
    result = sample->SetSampleTime(MFGetSystemTime());
    if (FAILED(result)) return result;
    result = sample->SetSampleDuration(kFrameDuration);
    if (FAILED(result)) return result;
    if (token) {
        result = sample->SetUnknown(MFSampleExtension_Token, token);
        if (FAILED(result)) return result;
    }
    auto events = events_;
    lock.unlock();
    result = events->QueueEventParamUnk(MEMediaSample, GUID_NULL, S_OK, sample.get());
    return result;
}
HRESULT MediaStream::set_allocator(IUnknown* allocator) noexcept {
    if (!allocator) return E_POINTER;
    std::scoped_lock lock(mutex_);
    if (shutdown_) return MF_E_SHUTDOWN;
    if (state_ == MF_STREAM_STATE_RUNNING) return MF_E_INVALIDREQUEST;
    const HRESULT result = allocator->QueryInterface(IID_PPV_ARGS(allocator_.put()));
    allocator_initialized_ = false;
    return result;
}
HRESULT MediaStream::SetStreamState(MF_STREAM_STATE state) noexcept {
    std::scoped_lock lock(mutex_);
    if (shutdown_) return MF_E_SHUTDOWN;
    if (state != MF_STREAM_STATE_RUNNING && state != MF_STREAM_STATE_STOPPED &&
        state != MF_STREAM_STATE_PAUSED) {
        return MF_E_INVALID_STATE_TRANSITION;
    }
    state_ = state;
    return S_OK;
}
HRESULT MediaStream::GetStreamState(MF_STREAM_STATE* state) noexcept {
    if (!state) return E_POINTER;
    std::scoped_lock lock(mutex_);
    if (shutdown_) return MF_E_SHUTDOWN;
    *state = state_;
    return S_OK;
}
HRESULT MediaStream::start(LONGLONG start_time) noexcept {
    std::unique_lock lock(mutex_);
    if (shutdown_) return MF_E_SHUTDOWN;
    if (allocator_ && !allocator_initialized_) {
        winrt::com_ptr<IMFMediaTypeHandler> handler;
        winrt::com_ptr<IMFMediaType> media_type;
        HRESULT result = descriptor_->GetMediaTypeHandler(handler.put());
        if (SUCCEEDED(result)) result = handler->GetCurrentMediaType(media_type.put());
        if (SUCCEEDED(result)) result = allocator_->InitializeSampleAllocator(10, media_type.get());
        if (FAILED(result)) return result;
        allocator_initialized_ = true;
    }
    state_ = MF_STREAM_STATE_RUNNING;
    sample_time_ = start_time;
    PROPVARIANT start;
    PropVariantInit(&start);
    start.vt = VT_I8;
    start.hVal.QuadPart = start_time;
    auto events = events_;
    lock.unlock();
    return events->QueueEventParamVar(MEStreamStarted, GUID_NULL, S_OK, &start);
}
HRESULT MediaStream::stop() noexcept {
    std::unique_lock lock(mutex_);
    if (shutdown_) return MF_E_SHUTDOWN;
    state_ = MF_STREAM_STATE_STOPPED;
    auto events = events_;
    lock.unlock();
    return events->QueueEventParamVar(MEStreamStopped, GUID_NULL, S_OK, nullptr);
}
HRESULT MediaStream::shutdown() noexcept {
    std::scoped_lock lock(mutex_);
    if (shutdown_) return S_OK;
    shutdown_ = true;
    state_ = MF_STREAM_STATE_STOPPED;
    reader_.close();
    if (allocator_ && allocator_initialized_) allocator_->UninitializeSampleAllocator();
    allocator_initialized_ = false;
    allocator_ = nullptr;
    if (events_) events_->Shutdown();
    events_ = nullptr;
    descriptor_ = nullptr;
    source_ = nullptr;
    return S_OK;
}

HRESULT MediaSource::initialize(IMFAttributes* activation_attributes) noexcept {
    HRESULT result = MFCreateEventQueue(events_.put());
    if (FAILED(result)) return result;
    result = MFCreateAttributes(attributes_.put(), 8);
    if (FAILED(result)) return result;
    if (activation_attributes) activation_attributes->CopyAllItems(attributes_.get());

    winrt::com_ptr<IMFMediaType> type;
    result = MFCreateMediaType(type.put());
    if (FAILED(result)) return result;
    if (FAILED(result = type->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video))) return result;
    if (FAILED(result = type->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_NV12))) return result;
    if (FAILED(result = MFSetAttributeSize(type.get(), MF_MT_FRAME_SIZE, kWidth, kHeight))) return result;
    if (FAILED(result = MFSetAttributeRatio(type.get(), MF_MT_FRAME_RATE, kFps, 1))) return result;
    if (FAILED(result = MFSetAttributeRatio(type.get(), MF_MT_PIXEL_ASPECT_RATIO, 1, 1))) return result;
    if (FAILED(result = type->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive))) return result;
    if (FAILED(result = type->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT, TRUE))) return result;

    IMFMediaType* types[] = {type.get()};
    winrt::com_ptr<IMFStreamDescriptor> descriptor;
    result = MFCreateStreamDescriptor(kStreamId, 1, types, descriptor.put());
    if (FAILED(result)) return result;
    descriptor->SetGUID(MF_DEVICESTREAM_STREAM_CATEGORY, PINNAME_VIDEO_CAPTURE);
    descriptor->SetUINT32(MF_DEVICESTREAM_STREAM_ID, kStreamId);
    descriptor->SetUINT32(MF_DEVICESTREAM_FRAMESERVER_SHARED, 1);
    descriptor->SetUINT32(MF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES, MFFrameSourceTypes_Color);

    IMFStreamDescriptor* descriptors[] = {descriptor.get()};
    result = MFCreatePresentationDescriptor(1, descriptors, presentation_.put());
    if (FAILED(result)) return result;
    presentation_->SelectStream(0);

    stream_ = winrt::make_self<MediaStream>();
    result = stream_->initialize(this, descriptor.get());
    return result;
}

HRESULT MediaSource::GetEvent(DWORD flags, IMFMediaEvent** event) noexcept { return events_ ? events_->GetEvent(flags, event) : MF_E_SHUTDOWN; }
HRESULT MediaSource::BeginGetEvent(IMFAsyncCallback* callback, IUnknown* state) noexcept { return events_ ? events_->BeginGetEvent(callback, state) : MF_E_SHUTDOWN; }
HRESULT MediaSource::EndGetEvent(IMFAsyncResult* result, IMFMediaEvent** event) noexcept { return events_ ? events_->EndGetEvent(result, event) : MF_E_SHUTDOWN; }
HRESULT MediaSource::QueueEvent(MediaEventType type, REFGUID extended_type, HRESULT status, const PROPVARIANT* value) noexcept { return events_ ? events_->QueueEventParamVar(type, extended_type, status, value) : MF_E_SHUTDOWN; }
HRESULT MediaSource::GetCharacteristics(DWORD* characteristics) noexcept {
    if (!characteristics) return E_POINTER;
    *characteristics = MFMEDIASOURCE_IS_LIVE;
    return S_OK;
}
HRESULT MediaSource::CreatePresentationDescriptor(IMFPresentationDescriptor** descriptor) noexcept {
    if (!descriptor) return E_POINTER;
    *descriptor = nullptr;
    std::scoped_lock lock(mutex_);
    if (state_ == State::shutdown) return MF_E_SHUTDOWN;
    return presentation_->Clone(descriptor);
}
HRESULT MediaSource::Start(IMFPresentationDescriptor* descriptor, const GUID* time_format,
                           const PROPVARIANT* start_position) noexcept {
    if (!descriptor || !start_position) return E_POINTER;
    if (time_format && *time_format != GUID_NULL) return MF_E_UNSUPPORTED_TIME_FORMAT;
    std::unique_lock lock(mutex_);
    if (state_ == State::shutdown) return MF_E_SHUTDOWN;
    if (start_position->vt != VT_EMPTY && start_position->vt != VT_I8) return MF_E_UNSUPPORTED_TIME_FORMAT;

    const auto stream_event = stream_announced_ ? MEUpdatedStream : MENewStream;
    stream_announced_ = true;
    state_ = State::started;
    auto stream = stream_;
    auto events = events_;
    lock.unlock();

    const LONGLONG start_time = MFGetSystemTime();
    HRESULT result = stream->SetStreamState(MF_STREAM_STATE_RUNNING);
    if (FAILED(result)) return result;
    result = events->QueueEventParamUnk(
        stream_event, GUID_NULL, S_OK, static_cast<IMFMediaStream2*>(stream.get()));
    if (FAILED(result)) return result;
    result = stream->start(start_time);
    if (FAILED(result)) return result;
    PROPVARIANT source_start;
    PropVariantInit(&source_start);
    source_start.vt = VT_I8;
    source_start.hVal.QuadPart = start_time;
    result = events->QueueEventParamVar(MESourceStarted, GUID_NULL, S_OK, &source_start);
    return result;
}
HRESULT MediaSource::Stop() noexcept {
    std::unique_lock lock(mutex_);
    if (state_ == State::shutdown) return MF_E_SHUTDOWN;
    state_ = State::stopped;
    auto stream = stream_;
    auto events = events_;
    lock.unlock();
    HRESULT result = stream->stop();
    if (FAILED(result)) return result;
    return events->QueueEventParamVar(MESourceStopped, GUID_NULL, S_OK, nullptr);
}
HRESULT MediaSource::Pause() noexcept { return MF_E_INVALID_STATE_TRANSITION; }
HRESULT MediaSource::Shutdown() noexcept {
    std::scoped_lock lock(mutex_);
    if (state_ == State::shutdown) return S_OK;
    state_ = State::shutdown;
    if (stream_) stream_->shutdown();
    stream_ = nullptr;
    if (events_) events_->Shutdown();
    events_ = nullptr;
    presentation_ = nullptr;
    attributes_ = nullptr;
    return S_OK;
}
HRESULT MediaSource::GetSourceAttributes(IMFAttributes** attributes) noexcept {
    if (!attributes) return E_POINTER;
    *attributes = nullptr;
    std::scoped_lock lock(mutex_);
    if (state_ == State::shutdown) return MF_E_SHUTDOWN;
    attributes_->AddRef();
    *attributes = attributes_.get();
    return S_OK;
}
HRESULT MediaSource::GetStreamAttributes(DWORD stream_id, IMFAttributes** attributes) noexcept {
    if (!attributes) return E_POINTER;
    *attributes = nullptr;
    if (stream_id != kStreamId) return MF_E_INVALIDSTREAMNUMBER;
    std::scoped_lock lock(mutex_);
    if (state_ == State::shutdown) return MF_E_SHUTDOWN;
    winrt::com_ptr<IMFStreamDescriptor> descriptor;
    HRESULT result = stream_->GetStreamDescriptor(descriptor.put());
    if (FAILED(result)) return result;
    return descriptor->QueryInterface(IID_PPV_ARGS(attributes));
}
HRESULT MediaSource::SetD3DManager(IUnknown*) noexcept { return S_OK; }
HRESULT MediaSource::SetMediaType(DWORD stream_id, IMFMediaType* media_type) noexcept {
    if (!media_type) return E_POINTER;
    if (stream_id != kStreamId) return MF_E_INVALIDSTREAMNUMBER;
    winrt::com_ptr<IMFStreamDescriptor> descriptor;
    HRESULT result = stream_->GetStreamDescriptor(descriptor.put());
    if (FAILED(result)) return result;
    winrt::com_ptr<IMFMediaTypeHandler> handler;
    result = descriptor->GetMediaTypeHandler(handler.put());
    if (FAILED(result)) return result;
    return handler->SetCurrentMediaType(media_type);
}
HRESULT MediaSource::SetDefaultAllocator(DWORD stream_id, IUnknown* allocator) noexcept {
    if (stream_id != kStreamId) return MF_E_INVALIDSTREAMNUMBER;
    return stream_->set_allocator(allocator);
}
HRESULT MediaSource::GetAllocatorUsage(DWORD stream_id, DWORD* input_stream_id,
                                       MFSampleAllocatorUsage* usage) noexcept {
    if (!input_stream_id || !usage) return E_POINTER;
    if (stream_id != kStreamId) return MF_E_INVALIDSTREAMNUMBER;
    *input_stream_id = kStreamId;
    *usage = MFSampleAllocatorUsage_UsesProvidedAllocator;
    return S_OK;
}
HRESULT MediaSource::GetService(REFGUID, REFIID, LPVOID* object) noexcept {
    if (!object) return E_POINTER;
    *object = nullptr;
    return MF_E_UNSUPPORTED_SERVICE;
}
HRESULT MediaSource::KsProperty(PKSPROPERTY, ULONG, LPVOID, ULONG, ULONG* bytes_returned) noexcept {
    if (bytes_returned) *bytes_returned = 0;
    return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}
HRESULT MediaSource::KsMethod(PKSMETHOD, ULONG, LPVOID, ULONG, ULONG* bytes_returned) noexcept {
    if (bytes_returned) *bytes_returned = 0;
    return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}
HRESULT MediaSource::KsEvent(PKSEVENT, ULONG, LPVOID, ULONG, ULONG* bytes_returned) noexcept {
    if (bytes_returned) *bytes_returned = 0;
    return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}

Activation::Activation() {
    winrt::check_hresult(MFCreateAttributes(attributes_.put(), 16));
}
HRESULT Activation::ActivateObject(REFIID iid, void** object) noexcept {
    if (!object) return E_POINTER;
    *object = nullptr;
    try {
        if (!active_source_) {
            active_source_ = winrt::make_self<MediaSource>();
            winrt::check_hresult(active_source_->initialize(attributes_.get()));
        }
        return active_source_->QueryInterface(iid, object);
    } catch (...) { return winrt::to_hresult(); }
}
HRESULT Activation::ShutdownObject() noexcept {
    if (active_source_) active_source_->Shutdown();
    active_source_ = nullptr;
    return S_OK;
}
HRESULT Activation::DetachObject() noexcept { active_source_ = nullptr; return S_OK; }

#define MFVC_FORWARD(method, ...) return attributes_->method(__VA_ARGS__)
HRESULT Activation::GetItem(REFGUID k, PROPVARIANT* v) noexcept { MFVC_FORWARD(GetItem, k, v); }
HRESULT Activation::GetItemType(REFGUID k, MF_ATTRIBUTE_TYPE* v) noexcept { MFVC_FORWARD(GetItemType, k, v); }
HRESULT Activation::CompareItem(REFGUID k, REFPROPVARIANT v, BOOL* r) noexcept { MFVC_FORWARD(CompareItem, k, v, r); }
HRESULT Activation::Compare(IMFAttributes* t, MF_ATTRIBUTES_MATCH_TYPE m, BOOL* r) noexcept { MFVC_FORWARD(Compare, t, m, r); }
HRESULT Activation::GetUINT32(REFGUID k, UINT32* v) noexcept { MFVC_FORWARD(GetUINT32, k, v); }
HRESULT Activation::GetUINT64(REFGUID k, UINT64* v) noexcept { MFVC_FORWARD(GetUINT64, k, v); }
HRESULT Activation::GetDouble(REFGUID k, double* v) noexcept { MFVC_FORWARD(GetDouble, k, v); }
HRESULT Activation::GetGUID(REFGUID k, GUID* v) noexcept { MFVC_FORWARD(GetGUID, k, v); }
HRESULT Activation::GetStringLength(REFGUID k, UINT32* v) noexcept { MFVC_FORWARD(GetStringLength, k, v); }
HRESULT Activation::GetString(REFGUID k, LPWSTR v, UINT32 s, UINT32* l) noexcept { MFVC_FORWARD(GetString, k, v, s, l); }
HRESULT Activation::GetAllocatedString(REFGUID k, LPWSTR* v, UINT32* l) noexcept { MFVC_FORWARD(GetAllocatedString, k, v, l); }
HRESULT Activation::GetBlobSize(REFGUID k, UINT32* v) noexcept { MFVC_FORWARD(GetBlobSize, k, v); }
HRESULT Activation::GetBlob(REFGUID k, UINT8* v, UINT32 s, UINT32* l) noexcept { MFVC_FORWARD(GetBlob, k, v, s, l); }
HRESULT Activation::GetAllocatedBlob(REFGUID k, UINT8** v, UINT32* s) noexcept { MFVC_FORWARD(GetAllocatedBlob, k, v, s); }
HRESULT Activation::GetUnknown(REFGUID k, REFIID i, LPVOID* v) noexcept { MFVC_FORWARD(GetUnknown, k, i, v); }
HRESULT Activation::SetItem(REFGUID k, REFPROPVARIANT v) noexcept { MFVC_FORWARD(SetItem, k, v); }
HRESULT Activation::DeleteItem(REFGUID k) noexcept { MFVC_FORWARD(DeleteItem, k); }
HRESULT Activation::DeleteAllItems() noexcept { MFVC_FORWARD(DeleteAllItems); }
HRESULT Activation::SetUINT32(REFGUID k, UINT32 v) noexcept { MFVC_FORWARD(SetUINT32, k, v); }
HRESULT Activation::SetUINT64(REFGUID k, UINT64 v) noexcept { MFVC_FORWARD(SetUINT64, k, v); }
HRESULT Activation::SetDouble(REFGUID k, double v) noexcept { MFVC_FORWARD(SetDouble, k, v); }
HRESULT Activation::SetGUID(REFGUID k, REFGUID v) noexcept { MFVC_FORWARD(SetGUID, k, v); }
HRESULT Activation::SetString(REFGUID k, LPCWSTR v) noexcept { MFVC_FORWARD(SetString, k, v); }
HRESULT Activation::SetBlob(REFGUID k, const UINT8* v, UINT32 s) noexcept { MFVC_FORWARD(SetBlob, k, v, s); }
HRESULT Activation::SetUnknown(REFGUID k, IUnknown* v) noexcept { MFVC_FORWARD(SetUnknown, k, v); }
HRESULT Activation::LockStore() noexcept { MFVC_FORWARD(LockStore); }
HRESULT Activation::UnlockStore() noexcept { MFVC_FORWARD(UnlockStore); }
HRESULT Activation::GetCount(UINT32* v) noexcept { MFVC_FORWARD(GetCount, v); }
HRESULT Activation::GetItemByIndex(UINT32 i, GUID* k, PROPVARIANT* v) noexcept { MFVC_FORWARD(GetItemByIndex, i, k, v); }
HRESULT Activation::CopyAllItems(IMFAttributes* v) noexcept { MFVC_FORWARD(CopyAllItems, v); }
#undef MFVC_FORWARD

HRESULT ClassFactory::CreateInstance(IUnknown* outer, REFIID iid, void** object) noexcept {
    if (!object) return E_POINTER;
    *object = nullptr;
    if (outer) return CLASS_E_NOAGGREGATION;
    try { return winrt::make_self<Activation>()->QueryInterface(iid, object); }
    catch (...) { return winrt::to_hresult(); }
}
HRESULT ClassFactory::LockServer(BOOL) noexcept { return S_OK; }

}  // namespace mfvc
