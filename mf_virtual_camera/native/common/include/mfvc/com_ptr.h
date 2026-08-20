#pragma once

#include <unknwn.h>
#include <utility>

namespace mfvc {

template <typename T>
class ComPtr final {
public:
    ComPtr() noexcept = default;
    ~ComPtr() { reset(); }

    ComPtr(const ComPtr&) = delete;
    ComPtr& operator=(const ComPtr&) = delete;

    ComPtr(ComPtr&& other) noexcept : value_(std::exchange(other.value_, nullptr)) {}
    ComPtr& operator=(ComPtr&& other) noexcept {
        if (this != &other) {
            reset();
            value_ = std::exchange(other.value_, nullptr);
        }
        return *this;
    }

    [[nodiscard]] T* get() const noexcept { return value_; }
    [[nodiscard]] T* operator->() const noexcept { return value_; }
    [[nodiscard]] explicit operator bool() const noexcept { return value_ != nullptr; }

    T** put() noexcept {
        reset();
        return &value_;
    }

    void reset(T* value = nullptr) noexcept {
        if (value_) {
            value_->Release();
        }
        value_ = value;
    }

private:
    T* value_ = nullptr;
};

}  // namespace mfvc

