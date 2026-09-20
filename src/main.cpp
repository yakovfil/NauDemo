#include <filesystem>

#include "demo_scene.h"
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
        CubeDemo() :
            SampleAppDelegate("sceneBase")
        {
        }

    private:
        nau::Result<> configureApplication() override
        {
            auto& properties = nau::getServiceProvider().get<nau::GlobalProperties>();
            properties
                .setValue("sampleProjectDir",
                          eastl::string(NAU_ENGINE_DIR "/samples/sceneBase"))
                .ignore();
            properties.setValue("demoProjectDir", eastl::string(NAU_DEMO_DIR)).ignore();
            NauCheckResult(nau::mergePropertiesFromFile(
                properties, std::filesystem::path(NAU_DEMO_DIR) / "config/app.json"));
            return nau::applyDefaultAppConfiguration();
        }

        nau::Result<> initializeServices() override
        {
            return nau::ResultSuccess;
        }

        void onApplicationInitialized() override
        {
            auto& window =
                nau::getServiceProvider().get<nau::IWindowManager>().getActiveWindow();
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
            m_scene = nau::demo::createCubeScene(factory, *scene);
            auto& root = scene->getRoot();
            m_scene.cube->getRootComponent<StaticMeshComponent>().setMaterial(
                MaterialAssetRef("file:/demo/cube.nmat_json"));
            auto& camera = m_scene.camera->getRootComponent<CameraComponent>();

            auto& lightObject = root.attachChild(
                factory.createSceneObject<DirectionalLightComponent>());
            lightObject.setRotation(math::quat::rotationZ(-0.8f));
            lightObject.getRootComponent<DirectionalLightComponent>().setIntensity(
                2.0f);

            auto& environment = root.addComponent<EnvironmentComponent>();
            environment.setIntensity(0.5f);
            environment.setTextureAsset(TextureAssetRef(
                "file:/content/textures/environment/SunnyHills_2k.hdr"));

            co_await getServiceProvider().get<ISceneManager>().activateScene(
                std::move(scene));
            getServiceProvider().get<ICameraManager>().setMainCamera(camera);
        }

        void onApplicationStep(std::chrono::milliseconds dt) override
        {
            m_scene.advance(dt);
        }

        nau::demo::CubeScene m_scene;
    };
}  // namespace

int main()
{
    return nau::runApplication(eastl::make_unique<CubeDemo>());
}
