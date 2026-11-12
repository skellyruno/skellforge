"""SkellForge v0.3: stable parameter catalog and generated real-time DSP.

Studio is the owner of the document, this module never modifies plug-in source.
Parameter IDs are generated from stable node IDs, and kept in a monotonic registry
so bypass/removal cannot silently steal or renumber automation.
"""
from __future__ import annotations

import math
import re
from copy import deepcopy

SPEC = {
    "saturate": {"field": "drive", "minimum": 1.0, "maximum": 10.0, "step": 0.1},
    "lowpass": {"field": "cutoff_hz", "minimum": 20.0, "maximum": 20000.0, "step": 1.0},
}
PARAM_ID = re.compile(r"fx_([a-z][a-z0-9_]{0,31})_(drive|cutoff_hz)\Z")


class ParameterError(ValueError):
    pass


def spec_for(node: dict) -> dict | None:
    kind = node["type"]
    if kind not in SPEC:
        return None
    template = SPEC[kind]
    return {
        "id": f"fx_{node['id']}_{template['field']}",
        "node": node["id"],
        "kind": kind,
        "field": template["field"],
        "minimum": template["minimum"],
        "maximum": template["maximum"],
        "step": template["step"],
        "default": float(node[template["field"]]),
    }


def active_specs(data: dict) -> list[dict]:
    return [s for n in data["chain"][1:] if (s := spec_for(n)) is not None]


def _identity(spec: dict) -> tuple:
    return (spec["id"], spec["node"], spec["kind"], spec["field"],
            spec["minimum"], spec["maximum"], spec["step"], spec["default"])


def registry_specs(data: dict) -> list[dict]:
    raw = data.get("parameter_registry", [])
    if not isinstance(raw, list) or len(raw) > 64:
        raise ParameterError("parameter_registry must be a bounded list of 0–64 entries")
    result = []
    seen = set()
    for spec in raw:
        if not isinstance(spec, dict):
            raise ParameterError("Malformed parameter registry entry")
        pid = spec.get("id")
        if not isinstance(pid, str) or not PARAM_ID.fullmatch(pid) or pid in seen:
            raise ParameterError("Invalid or duplicate reserved parameter identifier")
        seen.add(pid)
        kind = spec.get("kind")
        if kind not in SPEC:
            raise ParameterError("Unknown reserved DSP parameter kind")
        template = SPEC[kind]
        node = spec.get("node")
        if not isinstance(node, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", node):
            raise ParameterError("Invalid reserved DSP node ID")
        if pid != f"fx_{node}_{template['field']}":
            raise ParameterError("Reserved parameter identity mismatch")
        for key in ("minimum", "maximum", "step"):
            if type(spec.get(key)) not in (int, float) or float(spec[key]) != template[key]:
                raise ParameterError("Reserved parameter range cannot change")
        value = spec.get("default")
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ParameterError("Reserved parameter default must be finite")
        if not template["minimum"] <= value <= template["maximum"]:
            raise ParameterError("Reserved parameter default outside fixed bounds")
        if spec.get("field") != template["field"]:
            raise ParameterError("Reserved parameter field cannot change")
        result.append({
            "id": pid, "node": node, "kind": kind,
            "field": template["field"], "minimum": template["minimum"],
            "maximum": template["maximum"], "step": template["step"],
            "default": float(value),
        })
    return result


def unified_specs(data: dict) -> list[dict]:
    """Immutable registry entries first, append brand new parameters afterward."""
    specs = registry_specs(data)
    existing = {s["id"]: s for s in specs}
    for spec in active_specs(data):
        old = existing.get(spec["id"])
        if old is None:
            specs.append(spec)
            existing[spec["id"]] = spec
        elif (old["kind"], old["node"], old["field"]) != (spec["kind"], spec["node"], spec["field"]):
            raise ParameterError(f"Cannot reuse previously reserved parameter {spec['id']}")
        elif old["default"] != spec["default"]:
            raise ParameterError(
                f"Parameter default is locked after first save: {spec['id']}. "
                "Change the knob in the DAW instead.")
    return specs


def sync_registry(data: dict, previous: dict | None = None) -> None:
    """Add current and historical specs, never remove; mutates the supplied data.

    Before deleting an effect, Studio saves it as a retired parameter with its
    original default and range. DAW projects can still load the previous parameter.
    Graph code simply ignores a retired parameter.
    """
    old = previous or {"chain": [{"id": "gain", "type": "gain", "enabled": True}]}
    combined = []
    existing = {}
    for item in unified_specs(old) + unified_specs(data):
        prior = existing.get(item["id"])
        if prior is None:
            entry = deepcopy(item)
            combined.append(entry)
            existing[item["id"]] = entry
        elif (prior["node"], prior["kind"], prior["field"]) != (
                item["node"], item["kind"], item["field"]):
            raise ParameterError("Reserved parameter ID collision")
    # A saved ID belongs to its historical node even after deletion.
    # Do not permit reviving it as a new node with an unrelated meaning.
    former_live = {node["id"] for node in old["chain"]}
    former_reserved = {entry["node"] for entry in unified_specs(old)}
    for node in data["chain"][1:]:
        if node["id"] in former_reserved and node["id"] not in former_live:
            raise ParameterError(f"Reusing retired DSP node ID is forbidden: {node['id']}")
    data["parameter_registry"] = combined


def available_parameters(data: dict) -> list[dict]:
    return active_specs(data)


def _flt(value: float) -> str:
    text = format(float(value), ".9g")
    if "e" not in text.lower() and "." not in text:
        text += ".0"
    return text


def render_parameters(data: dict, header: str) -> str:
    lines = [
        header,
        "#pragma once\n#include <juce_audio_processors/juce_audio_processors.h>\n",
        "#include <memory>\n",
        "namespace forgeparams {\n",
        "inline void append(juce::AudioProcessorValueTreeState::ParameterLayout& layout) {\n",
    ]
    for spec in unified_specs(data):
        name = f"{spec['node']} {spec['field']}"
        lines.extend([
            "    layout.add(std::make_unique<juce::AudioParameterFloat>(\n",
            f'        juce::ParameterID{{"{spec["id"]}", 1}}, "{name}",\n',
            f"        juce::NormalisableRange<float>({_flt(spec['minimum'])}f, "
            f"{_flt(spec['maximum'])}f, {_flt(spec['step'])}f), "
            f"{_flt(spec['default'])}f));\n",
        ])
    lines.append("}\n} // namespace forgeparams\n")
    return "".join(lines)


def render_graph(data: dict, header: str) -> str:
    """Actual JUCE block processor. No allocations/locks in process()."""
    active = [n for n in data["chain"][1:] if n["enabled"]]
    lines = [
        header,
        "#pragma once\n#include <JuceHeader.h>\n",
        "#include <algorithm>\n#include <array>\n#include <atomic>\n#include <cmath>\n",
        "namespace forgedsp {\nclass Graph {\npublic:\n",
        "    void bind(juce::AudioProcessorValueTreeState& parameters) noexcept {\n",
    ]
    for idx, node in enumerate(active):
        spec = spec_for(node)
        lines.append(
            f'        ptr_{idx}_ = parameters.getRawParameterValue("{spec["id"]}");\n'
        )
    lines.extend(["        (void)parameters;\n    }\n",
                  "    void prepare(double sampleRate) noexcept {\n",
                  "        rate_ = std::isfinite(sampleRate) && sampleRate > 1000.0"
                  " ? std::min(sampleRate, 192000.0) : 48000.0;\n"])
    for idx, node in enumerate(active):
        spec = spec_for(node)
        lines.extend([
            f"        smooth_{idx}_.reset(rate_, 0.020);\n",
            f"        smooth_{idx}_.setCurrentAndTargetValue("
            f"read(ptr_{idx}_, {_flt(spec['default'])}f, "
            f"{_flt(spec['minimum'])}f, {_flt(spec['maximum'])}f));\n",
        ])
        if node["type"] == "lowpass":
            lines.append(f"        state_{idx}_.fill(0.0f);\n")
    lines.extend([
        "    }\n",
        "    void process(juce::AudioBuffer<float>& audio) noexcept {\n",
        "        const int frames = audio.getNumSamples();\n",
        "        const int channels = juce::jmin(audio.getNumChannels(), 2);\n",
        "        if (frames <= 0 || channels <= 0) return;\n",
    ])
    for idx, node in enumerate(active):
        spec = spec_for(node)
        lines.append(
            f"        smooth_{idx}_.setTargetValue("
            f"read(ptr_{idx}_, {_flt(spec['default'])}f, "
            f"{_flt(spec['minimum'])}f, {_flt(spec['maximum'])}f));\n"
        )
        if node["type"] == "saturate":
            lines.extend([
                f"        // {node['id']}: stable, host-automatable drive\n",
                "        for (int i = 0; i < frames; ++i) {\n",
                f"            const float drive = smooth_{idx}_.getNextValue();\n",
                "            const float normalizer = 1.0f / std::tanh(drive);\n",
                "            for (int ch = 0; ch < channels; ++ch) {\n",
                "                auto* ptr = audio.getWritePointer(ch);\n",
                "                const float sample = std::isfinite(ptr[i]) ? ptr[i] : 0.0f;\n",
                "                ptr[i] = std::tanh(sample * drive) * normalizer;\n",
                "            }\n        }\n",
            ])
        elif node["type"] == "lowpass":
            lines.extend([
                f"        // {node['id']}: smoothed cutoff; exp once per sample (prototype)\n",
                "        for (int i = 0; i < frames; ++i) {\n",
                f"            const double cutoff = std::min(static_cast<double>(smooth_{idx}_.getNextValue()), rate_ * 0.45);\n",
                "            const float coeff = static_cast<float>(std::exp(-6.283185307179586 * cutoff / rate_));\n",
                "            for (int ch = 0; ch < channels; ++ch) {\n",
                "                auto* ptr = audio.getWritePointer(ch);\n",
                "                const float sample = std::isfinite(ptr[i]) ? ptr[i] : 0.0f;\n",
                f"                float& state = state_{idx}_[static_cast<size_t>(ch)];\n",
                "                state = coeff * state + (1.0f - coeff) * sample;\n",
                "                if (std::abs(state) < 1.0e-20f) state = 0.0f;\n",
                "                ptr[i] = state;\n",
                "            }\n        }\n",
            ])
    lines.extend([
        "    }\nprivate:\n",
        "    static float read(const std::atomic<float>* ptr, float fallback,"
        " float minValue, float maxValue) noexcept {\n",
        "        const float value = ptr ? ptr->load(std::memory_order_relaxed) : fallback;\n",
        "        return std::isfinite(value) ? juce::jlimit(minValue, maxValue, value) : fallback;\n",
        "    }\n",
        "    double rate_ = 48000.0;\n",
    ])
    for idx, node in enumerate(active):
        spec = spec_for(node)
        lines.extend([
            f"    const std::atomic<float>* ptr_{idx}_ = nullptr;\n",
            f"    juce::SmoothedValue<float, juce::ValueSmoothingTypes::Linear>"
            f" smooth_{idx}_{{{_flt(spec['default'])}f}};\n",
        ])
        if node["type"] == "lowpass":
            lines.append(f"    std::array<float, 2> state_{idx}_{{}};\n")
    lines.append("};\n} // namespace forgedsp\n")
    return "".join(lines)
