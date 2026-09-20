#pragma once

#include <chrono>
#include <cmath>

#include "nau/assets/asset_ref.h"
#include "nau/scene/components/camera_component.h"
#include "nau/scene/components/static_mesh_component.h"
#include "nau/scene/scene_factory.h"

namespace nau::demo
{
    // Both adapters use the same Nau objects and simulation-time rotation.
    struct CubeScene
    {
        scene::ObjectWeakRef<scene::SceneObject> cube;
        scene::ObjectWeakRef<scene::SceneObject> camera;
        float angle = 0.35f;

        void advance(std::chrono::milliseconds dt)
        {
            if (cube)
            {
                constexpr float radiansPerSecond = 0.785398163f;
                angle = std::fmod(angle + std::chrono::duration<float>(dt).count() *
                                              radiansPerSecond,
                                  6.283185307f);
                cube->setRotation(math::quat::rotationY(angle));
            }
        }
    };

    inline CubeScene createCubeScene(scene::ISceneFactory& factory,
                                     scene::IScene& scene)
    {
        scene.setName("Rotating Cube");
        auto& root = scene.getRoot();
        auto& cube =
            root.attachChild(factory.createSceneObject<scene::StaticMeshComponent>());
        cube.setName("Cube");
        cube.getRootComponent<scene::StaticMeshComponent>().setMeshGeometry(
            StaticMeshAssetRef("file:/demo/cube.gltf+[mesh/0]"));

        auto& camera =
            root.attachChild(factory.createSceneObject<scene::CameraComponent>());
        camera.setName("Camera");
        // Nau's right-handed camera looks along local -Z.
        camera.setTranslation({0.0f, 3.0f, 9.0f});
        camera.setRotation(math::quat::rotationX(-0.322f));
        auto& component = camera.getRootComponent<scene::CameraComponent>();
        component.setFov(45.0f);
        component.setClipNearPlane(0.1f);
        component.setClipFarPlane(100.0f);
        CubeScene result{cube, camera};
        result.advance(std::chrono::milliseconds::zero());
        return result;
    }
}  // namespace nau::demo
