// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#include "free_camera.h"
#ifdef NAU_DEMO_PORTABLE_INPUT
    #include "free_camera_motion.h"
    #include "nau/input.h"
    #include "nau/scene/camera/camera_manager.h"
    #include "nau/scene/components/camera_component.h"
    #include "nau/scene/internal/scene_manager_internal.h"
    #include "nau/service/service_provider.h"
    #include "nau_project_policy.h"

void DemoFreeCamera::gamePreUpdate(std::chrono::milliseconds dt)
{
    if (std::string_view(nau::project::StartupConfiguration) == "/config/battlezone_scene.json") return;
    using namespace nau;
    using namespace nau::input;
    const auto held = [](Key key)
    {
        return isKeyboardButtonHold(0, key) ? 1.f : 0.f;
    };
    demo::CameraInput input;
    input.forward = held(Key::W) - held(Key::S);
    input.right = held(Key::D) - held(Key::A);
    input.vertical = held(Key::E) - held(Key::Q);
    input.drag = isMouseButtonHold(0, MouseKey::ButtonLeft);
    input.dx = getMouseAxisDelta(0, MouseKey::AxisX);
    input.dy = getMouseAxisDelta(0, MouseKey::AxisY);
    auto camera = getServiceProvider().get<scene::ICameraManager>().getCameras().getWorldMainCamera();
    if (!camera)
        return;
    // Resolve the selected live component every update; a snapshot is read-only
    // and retaining its underlying scene component could outlive scene removal.
    auto* component = getServiceProvider().get<scene::ISceneManagerInternal>().findComponent(camera->getCameraUid());
    auto* control = component ? component->as<scene::CameraComponent*>() : nullptr;
    if (!control)
        return;
    auto transform = control->getWorldTransform();
    if (demo::moveCamera(transform, input, static_cast<float>(dt.count()) / 1000.f))
        control->setWorldTransform(transform);
}
#endif
