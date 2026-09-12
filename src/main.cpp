#include <cmath>
#include <filesystem>

#include "nau/app/application.h"
#include "nau/app/global_properties.h"
#include "nau/app/platform_window.h"
#include "nau/app/run_application.h"
#include "nau/app/window_manager.h"
#include "nau/assets/asset_ref.h"
#include "nau/samples/sample_app_delegate.h"
#include "nau/scene/camera/camera_manager.h"
#include "nau/scene/components/camera_component.h"
#include "nau/scene/components/directional_light_component.h"
#include "nau/scene/components/environment_component.h"
#include "nau/scene/components/static_mesh_component.h"
#include "nau/scene/scene.h"
#include "nau/scene/scene_factory.h"
#include "nau/scene/scene_manager.h"
#include "nau/service/service_provider.h"

namespace
{
    class CubeDemo final : public nau::sample::SampleAppDelegate
    {
    public:
        CubeDemo() : SampleAppDelegate("sceneBase") {}

    private:
        nau::Result<> configureApplication() override
        {
            auto& properties = nau::getServiceProvider().get<nau::GlobalProperties>();
            properties.setValue("sampleProjectDir", eastl::string(NAU_ENGINE_DIR "/samples/sceneBase")).ignore();
            properties.setValue("demoProjectDir", eastl::string(NAU_DEMO_DIR)).ignore();
            NauCheckResult(nau::mergePropertiesFromFile(properties, std::filesystem::path(NAU_DEMO_DIR) / "config/app.json"));
            return nau::applyDefaultAppConfiguration();
        }

        nau::Result<> initializeServices() override
        {
            return nau::ResultSuccess;
        }

        void onApplicationInitialized() override
        {
            auto& window = nau::getServiceProvider().get<nau::IWindowManager>().getActiveWindow();
            window.setName("Nau Demo - Rotating Cube");
            window.setSize(1280, 720);
            SampleAppDelegate::onApplicationInitialized();
        }

        nau::async::Task<> startupApplication() override
        {
            using namespace nau;
            using namespace nau::scene;

            auto& factory = getServiceProvider().get<ISceneFactory>();
            auto scene = factory.createEmptyScene();
            scene->setName("Rotating Cube");
            auto& root = scene->getRoot();

            auto& cube = root.attachChild(factory.createSceneObject<StaticMeshComponent>());
            cube.setName("Cube");
            auto& mesh = cube.getRootComponent<StaticMeshComponent>();
            mesh.setMeshGeometry(StaticMeshAssetRef("file:/demo/cube.gltf+[mesh/0]"));
            mesh.setMaterial(MaterialAssetRef("file:/demo/cube.nmat_json"));
            m_cube = cube;

            auto& cameraObject = root.attachChild(factory.createSceneObject<CameraComponent>());
            // Nau's right-handed camera looks along local -Z.
            cameraObject.setTranslation({0.0f, 3.0f, 9.0f});
            cameraObject.setRotation(math::quat::rotationX(-0.322f));
            auto& camera = cameraObject.getRootComponent<CameraComponent>();
            camera.setFov(45.0f);
            camera.setClipNearPlane(0.1f);
            camera.setClipFarPlane(100.0f);

            auto& lightObject = root.attachChild(factory.createSceneObject<DirectionalLightComponent>());
            lightObject.setRotation(math::quat::rotationZ(-0.8f));
            lightObject.getRootComponent<DirectionalLightComponent>().setIntensity(2.0f);

            auto& environment = root.addComponent<EnvironmentComponent>();
            environment.setIntensity(0.5f);
            environment.setTextureAsset(TextureAssetRef("file:/content/textures/environment/SunnyHills_2k.hdr"));

            co_await getServiceProvider().get<ISceneManager>().activateScene(std::move(scene));
            getServiceProvider().get<ICameraManager>().setMainCamera(camera);
        }

        void onApplicationStep(std::chrono::milliseconds dt) override
        {
            if (m_cube)
            {
                // Y is vertical. 45 degrees/second gives one full revolution every 8 seconds.
                constexpr float radiansPerSecond = 0.785398163f;
                m_angle = std::fmod(m_angle + std::chrono::duration<float>(dt).count() * radiansPerSecond, 6.283185307f);
                m_cube->setRotation(nau::math::quat::rotationY(m_angle));
            }
        }

        nau::scene::ObjectWeakRef<nau::scene::SceneObject> m_cube;
        float m_angle = 0.35f;
    };
}

int main()
{
    return nau::runApplication(eastl::make_unique<CubeDemo>());
}
