#pragma once

#include <Windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfobjects.h>
#include <ks.h>
#include <ksproxy.h>
#include <unknwn.h>
#include <winrt/base.h>

#include <atomic>
#include <mutex>

#include "mfvc/shared_frame_reader.h"

namespace mfvc {

inline constexpr GUID kMediaSourceGuid{
    0x7c81c5d6, 0x7424, 0x47dc, {0x8f, 0x4d, 0x12, 0x26, 0x15, 0x22, 0xc2, 0x39}};
inline constexpr GUID kWeComTestMediaSourceGuid{
    0xe98467c5, 0x18b5, 0x46b3, {0x94, 0x08, 0x1c, 0xe4, 0xc5, 0xc5, 0x94, 0x37}};

class MediaSource;

class MediaStream : public winrt::implements<MediaStream, IMFMediaStream2, IMFMediaStream> {
public:
    HRESULT initialize(MediaSource* source, IMFStreamDescriptor* descriptor) noexcept;
    HRESULT start(LONGLONG start_time) noexcept;
    HRESULT stop() noexcept;
    HRESULT shutdown() noexcept;
    HRESULT set_allocator(IUnknown* allocator) noexcept;

    HRESULT __stdcall GetEvent(DWORD flags, IMFMediaEvent** event) noexcept override;
    HRESULT __stdcall BeginGetEvent(IMFAsyncCallback* callback, IUnknown* state) noexcept override;
    HRESULT __stdcall EndGetEvent(IMFAsyncResult* result, IMFMediaEvent** event) noexcept override;
    HRESULT __stdcall QueueEvent(MediaEventType type, REFGUID extended_type, HRESULT status,
                                 const PROPVARIANT* value) noexcept override;
    HRESULT __stdcall GetMediaSource(IMFMediaSource** source) noexcept override;
    HRESULT __stdcall GetStreamDescriptor(IMFStreamDescriptor** descriptor) noexcept override;
    HRESULT __stdcall RequestSample(IUnknown* token) noexcept override;
    HRESULT __stdcall SetStreamState(MF_STREAM_STATE state) noexcept override;
    HRESULT __stdcall GetStreamState(MF_STREAM_STATE* state) noexcept override;

private:
    std::mutex mutex_;
    winrt::com_ptr<MediaSource> source_;
    winrt::com_ptr<IMFStreamDescriptor> descriptor_;
    winrt::com_ptr<IMFMediaEventQueue> events_;
    winrt::com_ptr<IMFVideoSampleAllocator> allocator_;
    bool allocator_initialized_ = false;
    SharedFrameReader reader_;
    MF_STREAM_STATE state_ = MF_STREAM_STATE_STOPPED;
    bool shutdown_ = false;
    LONGLONG sample_time_ = 0;
    std::uint64_t last_sequence_ = 0;
    ULONGLONG last_fresh_tick_ = 0;
};

class MediaSource : public winrt::implements<MediaSource, IMFMediaSource2, IMFMediaSourceEx,
                                             IMFMediaSource, IMFSampleAllocatorControl,
                                             IMFGetService, IKsControl> {
public:
    HRESULT initialize(IMFAttributes* activation_attributes) noexcept;

    HRESULT __stdcall GetEvent(DWORD flags, IMFMediaEvent** event) noexcept override;
    HRESULT __stdcall BeginGetEvent(IMFAsyncCallback* callback, IUnknown* state) noexcept override;
    HRESULT __stdcall EndGetEvent(IMFAsyncResult* result, IMFMediaEvent** event) noexcept override;
    HRESULT __stdcall QueueEvent(MediaEventType type, REFGUID extended_type, HRESULT status,
                                 const PROPVARIANT* value) noexcept override;
    HRESULT __stdcall GetCharacteristics(DWORD* characteristics) noexcept override;
    HRESULT __stdcall CreatePresentationDescriptor(IMFPresentationDescriptor** descriptor) noexcept override;
    HRESULT __stdcall Start(IMFPresentationDescriptor* descriptor, const GUID* time_format,
                            const PROPVARIANT* start_position) noexcept override;
    HRESULT __stdcall Stop() noexcept override;
    HRESULT __stdcall Pause() noexcept override;
    HRESULT __stdcall Shutdown() noexcept override;
    HRESULT __stdcall GetSourceAttributes(IMFAttributes** attributes) noexcept override;
    HRESULT __stdcall GetStreamAttributes(DWORD stream_id, IMFAttributes** attributes) noexcept override;
    HRESULT __stdcall SetD3DManager(IUnknown* manager) noexcept override;
    HRESULT __stdcall SetMediaType(DWORD stream_id, IMFMediaType* media_type) noexcept override;
    HRESULT __stdcall SetDefaultAllocator(DWORD stream_id, IUnknown* allocator) noexcept override;
    HRESULT __stdcall GetAllocatorUsage(DWORD stream_id, DWORD* input_stream_id,
                                        MFSampleAllocatorUsage* usage) noexcept override;
    HRESULT __stdcall GetService(REFGUID service, REFIID iid, LPVOID* object) noexcept override;
    HRESULT __stdcall KsProperty(PKSPROPERTY property, ULONG property_length,
                                 LPVOID data, ULONG data_length,
                                 ULONG* bytes_returned) noexcept override;
    HRESULT __stdcall KsMethod(PKSMETHOD method, ULONG method_length,
                               LPVOID data, ULONG data_length,
                               ULONG* bytes_returned) noexcept override;
    HRESULT __stdcall KsEvent(PKSEVENT event, ULONG event_length,
                              LPVOID data, ULONG data_length,
                              ULONG* bytes_returned) noexcept override;

private:
    enum class State { stopped, started, shutdown };

    std::mutex mutex_;
    winrt::com_ptr<IMFMediaEventQueue> events_;
    winrt::com_ptr<IMFPresentationDescriptor> presentation_;
    winrt::com_ptr<IMFAttributes> attributes_;
    winrt::com_ptr<MediaStream> stream_;
    State state_ = State::stopped;
    bool stream_announced_ = false;
};

class Activation : public winrt::implements<Activation, IMFActivate, IMFAttributes> {
public:
    Activation();

    HRESULT __stdcall ActivateObject(REFIID iid, void** object) noexcept override;
    HRESULT __stdcall ShutdownObject() noexcept override;
    HRESULT __stdcall DetachObject() noexcept override;

    HRESULT __stdcall GetItem(REFGUID key, PROPVARIANT* value) noexcept override;
    HRESULT __stdcall GetItemType(REFGUID key, MF_ATTRIBUTE_TYPE* type) noexcept override;
    HRESULT __stdcall CompareItem(REFGUID key, REFPROPVARIANT value, BOOL* result) noexcept override;
    HRESULT __stdcall Compare(IMFAttributes* theirs, MF_ATTRIBUTES_MATCH_TYPE match_type, BOOL* result) noexcept override;
    HRESULT __stdcall GetUINT32(REFGUID key, UINT32* value) noexcept override;
    HRESULT __stdcall GetUINT64(REFGUID key, UINT64* value) noexcept override;
    HRESULT __stdcall GetDouble(REFGUID key, double* value) noexcept override;
    HRESULT __stdcall GetGUID(REFGUID key, GUID* value) noexcept override;
    HRESULT __stdcall GetStringLength(REFGUID key, UINT32* length) noexcept override;
    HRESULT __stdcall GetString(REFGUID key, LPWSTR value, UINT32 size, UINT32* length) noexcept override;
    HRESULT __stdcall GetAllocatedString(REFGUID key, LPWSTR* value, UINT32* length) noexcept override;
    HRESULT __stdcall GetBlobSize(REFGUID key, UINT32* size) noexcept override;
    HRESULT __stdcall GetBlob(REFGUID key, UINT8* buffer, UINT32 size, UINT32* blob_size) noexcept override;
    HRESULT __stdcall GetAllocatedBlob(REFGUID key, UINT8** buffer, UINT32* size) noexcept override;
    HRESULT __stdcall GetUnknown(REFGUID key, REFIID iid, LPVOID* value) noexcept override;
    HRESULT __stdcall SetItem(REFGUID key, REFPROPVARIANT value) noexcept override;
    HRESULT __stdcall DeleteItem(REFGUID key) noexcept override;
    HRESULT __stdcall DeleteAllItems() noexcept override;
    HRESULT __stdcall SetUINT32(REFGUID key, UINT32 value) noexcept override;
    HRESULT __stdcall SetUINT64(REFGUID key, UINT64 value) noexcept override;
    HRESULT __stdcall SetDouble(REFGUID key, double value) noexcept override;
    HRESULT __stdcall SetGUID(REFGUID key, REFGUID value) noexcept override;
    HRESULT __stdcall SetString(REFGUID key, LPCWSTR value) noexcept override;
    HRESULT __stdcall SetBlob(REFGUID key, const UINT8* buffer, UINT32 size) noexcept override;
    HRESULT __stdcall SetUnknown(REFGUID key, IUnknown* value) noexcept override;
    HRESULT __stdcall LockStore() noexcept override;
    HRESULT __stdcall UnlockStore() noexcept override;
    HRESULT __stdcall GetCount(UINT32* count) noexcept override;
    HRESULT __stdcall GetItemByIndex(UINT32 index, GUID* key, PROPVARIANT* value) noexcept override;
    HRESULT __stdcall CopyAllItems(IMFAttributes* destination) noexcept override;

private:
    winrt::com_ptr<IMFAttributes> attributes_;
    winrt::com_ptr<MediaSource> active_source_;
};

class ClassFactory : public winrt::implements<ClassFactory, IClassFactory> {
public:
    HRESULT __stdcall CreateInstance(IUnknown* outer, REFIID iid, void** object) noexcept override;
    HRESULT __stdcall LockServer(BOOL lock) noexcept override;
};

}  // namespace mfvc
