// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#pragma once
#include <algorithm>
#include <cmath>

#include "nau/math/transform.h"

namespace demo
{
    struct CameraInput
    {
        float forward = 0, right = 0, vertical = 0;
        float dx = 0, dy = 0;
        bool drag = false;
    };

    inline bool moveCamera(nau::math::Transform& transform, const CameraInput& input, float seconds)
    {
        using namespace nau::math;
        const bool rotating = input.drag && (input.dx != 0 || input.dy != 0);
        const bool translating = input.forward != 0 || input.right != 0 || input.vertical != 0;
        if (!rotating && !translating)
            return false;
        auto rotation = transform.getRotation();
        if (rotating)
        {
            const auto facing = rotate(rotation, Vector3(0, 0, -1));
            const float yaw = std::atan2(-float(facing.getX()), -float(facing.getZ()));
            const float pitch = std::asin(std::clamp(float(facing.getY()), -1.f, 1.f));
            constexpr float sensitivity = .004f;
            constexpr float pitchLimit = 1.553343f;  // 89 degrees.
            rotation = normalize(Quat::rotationY(yaw - input.dx * sensitivity) *
                                 Quat::rotationX(std::clamp(pitch - input.dy * sensitivity, -pitchLimit, pitchLimit)));
            transform.setRotation(rotation);
        }
        if (translating)
        {
            auto forward = rotate(rotation, Vector3(0, 0, -1));
            forward.setY(0);
            const float squared = float(lengthSqr(forward));
            if (squared <= 1.e-8f)
                forward = Vector3(0, 0, -1);
            else
                forward /= std::sqrt(squared);
            const auto right = cross(forward, Vector3(0, 1, 0));
            auto direction = forward * input.forward + right * input.right + Vector3(0, input.vertical, 0);
            const float magnitude = float(length(direction));
            if (magnitude > 0)
            {
                constexpr float speed = 3.f;
                const float elapsed = std::isfinite(seconds) ? std::clamp(seconds, 0.f, .05f) : 0;
                transform.addTranslation(direction * (speed * elapsed / magnitude));
            }
        }
        return true;
    }
}  // namespace demo
