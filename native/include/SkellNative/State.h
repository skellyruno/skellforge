#pragma once
// SkellNative SDK: bounded versioned parameter snapshot format.
// OFF AUDIO THREAD ONLY: this utility allocates and uses std::string/vector.
// Data is not encrypted or authenticated; checksum detects accidental damage.
#include <SkellNative/PluginApi.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace skellnative::sdk {

struct StateValue {
    std::string persistentId;
    float normalized = 0.0f;
};

struct StateSnapshot {
    std::vector<StateValue> parameters;
};

inline bool validStateId(const std::string& id) noexcept {
    if (id.empty() || id.size() > 64) return false;
    for (unsigned char ch : id) {
        const bool valid = (ch >= 'a' && ch <= 'z')
            || (ch >= 'A' && ch <= 'Z')
            || (ch >= '0' && ch <= '9')
            || ch == '_' || ch == '.' || ch == '-';
        if (!valid) return false;
    }
    return true;
}

inline std::uint32_t stateChecksum(const std::vector<std::uint8_t>& bytes,
                                   std::size_t count) noexcept {
    std::uint32_t hash = 2166136261u;  // FNV-1a, NOT a security MAC
    for (std::size_t i=0; i<count; ++i) {
        hash ^= bytes[i];
        hash *= 16777619u;
    }
    return hash;
}

inline void put16(std::vector<std::uint8_t>& b, std::uint16_t n) {
    b.push_back(static_cast<std::uint8_t>(n & 0xffu));
    b.push_back(static_cast<std::uint8_t>((n >> 8u) & 0xffu));
}
inline void put32(std::vector<std::uint8_t>& b, std::uint32_t n) {
    for (unsigned shift=0; shift<32; shift+=8)
        b.push_back(static_cast<std::uint8_t>((n >> shift) & 0xffu));
}
inline bool get16(const std::vector<std::uint8_t>& b, std::size_t& index,
                  std::uint16_t& value) noexcept {
    if (index > b.size() || b.size()-index < 2) return false;
    value = static_cast<std::uint16_t>(b[index]
                 | (static_cast<unsigned>(b[index+1]) << 8u));
    index += 2;
    return true;
}
inline bool get32(const std::vector<std::uint8_t>& b, std::size_t& index,
                  std::uint32_t& value) noexcept {
    if (index > b.size() || b.size()-index < 4) return false;
    value = 0;
    for (unsigned shift=0; shift<32; shift+=8)
        value |= static_cast<std::uint32_t>(b[index++]) << shift;
    return true;
}

// Caller supplies stable plugin identity; preserve this across versions.
inline std::optional<std::vector<std::uint8_t>> encodeState(
    const std::string& productId, const StateSnapshot& state) {
    if (!validStateId(productId) || state.parameters.size()>128) return std::nullopt;
    std::vector<std::uint8_t> out;
    out.reserve(16 + 65 * state.parameters.size() + productId.size());
    out.insert(out.end(), {'S','K','S','T'});
    put16(out, 1); // format version
    out.push_back(static_cast<std::uint8_t>(productId.size()));
    out.insert(out.end(), productId.begin(), productId.end());
    put16(out, static_cast<std::uint16_t>(state.parameters.size()));
    for (std::size_t i=0; i<state.parameters.size(); ++i) {
        const auto& value = state.parameters[i];
        if (!validStateId(value.persistentId) || !std::isfinite(value.normalized)
            || value.normalized<0.0f || value.normalized>1.0f) return std::nullopt;
        for (std::size_t j=0; j<i; ++j)
            if (state.parameters[j].persistentId==value.persistentId) return std::nullopt;
        out.push_back(static_cast<std::uint8_t>(value.persistentId.size()));
        out.insert(out.end(), value.persistentId.begin(), value.persistentId.end());
        std::uint32_t bits=0;
        static_assert(sizeof(bits)==sizeof(value.normalized), "float32 required");
        std::memcpy(&bits, &value.normalized, sizeof(bits));
        put32(out,bits);
    }
    put32(out,stateChecksum(out,out.size()));
    return out;
}

inline std::optional<StateSnapshot> decodeState(
    const std::string& expectedProductId, const std::vector<std::uint8_t>& bytes) {
    if (!validStateId(expectedProductId) || bytes.size()<13 || bytes.size()>16384)
        return std::nullopt;
    if (bytes[0]!='S' || bytes[1]!='K' || bytes[2]!='S' || bytes[3]!='T')
        return std::nullopt;
    std::size_t pos=4;
    std::uint16_t version=0;
    if (!get16(bytes,pos,version) || version!=1) return std::nullopt;
    if (pos>=bytes.size()-4) return std::nullopt;
    const std::size_t idSize=bytes[pos++];
    if (idSize==0 || idSize>64 || idSize>bytes.size()-pos-4) return std::nullopt;
    const std::string actualId(bytes.begin()+static_cast<std::ptrdiff_t>(pos),
                               bytes.begin()+static_cast<std::ptrdiff_t>(pos+idSize));
    if (actualId != expectedProductId) return std::nullopt;
    pos+=idSize;
    std::uint16_t count=0;
    if (!get16(bytes,pos,count) || count>128) return std::nullopt;
    StateSnapshot snapshot;
    snapshot.parameters.reserve(count);
    for (std::uint16_t i=0; i<count; ++i) {
        if (pos>=bytes.size()-4) return std::nullopt;
        const std::size_t n=bytes[pos++];
        if (n==0 || n>64 || n>bytes.size()-pos-4) return std::nullopt;
        std::string id(bytes.begin()+static_cast<std::ptrdiff_t>(pos),
                       bytes.begin()+static_cast<std::ptrdiff_t>(pos+n));
        if (!validStateId(id)) return std::nullopt;
        pos+=n;
        std::uint32_t bits=0;
        if (!get32(bytes,pos,bits)) return std::nullopt;
        float normalized=0.0f;
        std::memcpy(&normalized,&bits,sizeof(bits));
        if (!std::isfinite(normalized) || normalized<0.0f || normalized>1.0f)
            return std::nullopt;
        for (const auto& previous : snapshot.parameters)
            if (previous.persistentId==id) return std::nullopt;
        snapshot.parameters.push_back({std::move(id),normalized});
    }
    if (pos != bytes.size()-4) return std::nullopt;
    std::uint32_t checksum=0;
    if (!get32(bytes,pos,checksum)
        || checksum!=stateChecksum(bytes,bytes.size()-4)) return std::nullopt;
    return snapshot;
}

} // namespace skellnative::sdk
