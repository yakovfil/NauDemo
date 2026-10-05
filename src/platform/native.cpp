#include <filesystem>

#include "../demo_platform.h"
#include "nau/app/application_init_delegate.h"
#include "nau/app/global_properties.h"
#include "nau/app/platform_window.h"
#include "nau/app/window_manager.h"
#include "nau/input.h"
#include "nau/scene/components/directional_light_component.h"
#include "nau/scene/components/environment_component.h"
#include "nau/service/service_provider.h"
#include "nau/text/screen_text.h"

namespace nau::demo
{
    class NativePlatform final : public DemoPlatform
    {
        NAU_RTTI_CLASS(NativePlatform, DemoPlatform)
    public:
        Result<> configure() override
        {
            auto& properties = getServiceProvider().get<GlobalProperties>();
            properties.setValue("sampleProjectDir", std::string(NAU_SAMPLES_DIR "/sceneBase")).ignore();
            properties.setValue("demoProjectDir", std::string(NAU_DEMO_DIR)).ignore();
            NauCheckResult(mergePropertiesFromFile(properties, std::filesystem::path(NAU_DEMO_DIR) / "config/app.json"));
            return applyDefaultAppConfiguration();
        }
        void initialized() override
        {
            auto& window = getServiceProvider().get<IWindowManager>().getActiveWindow();
            window.setName("Nau Demo - Rotating Cube");
            window.setSize(1280, 720);
            window.setVisible(true);
            const auto [width, height] = window.getClientSize();
            input::setScreenResolution(width, height);
        }
        async::Task<> prepareAssets() override
        {
            co_return;
        }
        void decorateScene(scene::IScene& scene, CubeScene& cube) override
        {
            using namespace nau::scene;
            auto& factory = getServiceProvider().get<ISceneFactory>();
            auto& root = scene.getRoot();
            cube.cube->getRootComponent<StaticMeshComponent>().setMaterial(MaterialAssetRef("file:/demo/cube.nmat_json"));
            auto& light = root.attachChild(factory.createSceneObject<DirectionalLightComponent>());
            light.setRotation(math::quat::rotationZ(-0.8f));
            light.getRootComponent<DirectionalLightComponent>().setIntensity(2.0f);
            auto& environment = root.addComponent<EnvironmentComponent>();
            environment.setIntensity(0.5f);
            environment.setTextureAsset(TextureAssetRef("file:/content/textures/environment/SunnyHills_2k.hdr"));
        }
        async::Task<> presentStartup(CubeScene&) override
        {
            co_await getServiceProvider().get<text::ScreenText>().whenPresented();
        }
        Result<> present(CubeScene&) override
        {
            return {};
        }
    };
    std::unique_ptr<DemoPlatform> createDemoPlatform()
    {
        return std::make_unique<NativePlatform>();
    }
}  // namespace nau::demo
