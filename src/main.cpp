#include <atomic>
#include <filesystem>
#include <memory>
#include <string>

#include "demo_scene.h"
#include "demo_text.h"
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
    std::atomic_bool textFailed = false;
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
                          std::string(NAU_SAMPLES_DIR "/sceneBase"))
                .ignore();
            properties.setValue("demoProjectDir", std::string(NAU_DEMO_DIR)).ignore();
            NauCheckResult(nau::mergePropertiesFromFile(
                properties, std::filesystem::path(NAU_DEMO_DIR) / "config/app.json"));
            return nau::applyDefaultAppConfiguration();
        }

        nau::Result<> initializeServices() override
        {
            nau::getServiceProvider().addService<nau::text::ScreenText>();
            auto label = nau::demo::createDemoText();
            if (!label)
            {
                textFailed = true;
                NAU_LOG_ERROR("NauDemo text failed: {}", label.getError()->getMessage());
                return label.getError();
            }
            m_label = *label;
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
            auto submitted = demo::drawDemoText(m_label);
            if (!submitted)
            {
                failText(submitted.getError());
                co_return;
            }
            auto presented = co_await getServiceProvider().get<text::ScreenText>().whenPresented().doTry();
            if (!presented)
            {
                failText(presented.getError());
                co_return;
            }
            NAU_LOG_DEBUG("NauDemo text ready");
        }

        void failText(nau::Error::Ptr error)
        {
            textFailed = true;
            NAU_LOG_ERROR("NauDemo text failed: {}", error->getMessage());
            nau::getApplication().stop();
        }

        void onApplicationStep(std::chrono::milliseconds dt) override
        {
            m_scene.advance(std::getenv("NAU_DEMO_FREEZE") ? std::chrono::milliseconds(0) : dt);
            if (m_label && !nau::getApplication().isClosing())
            {
                auto drawn = nau::demo::drawDemoText(m_label);
                if (!drawn)
                    failText(drawn.getError());
            }
        }

        nau::demo::CubeScene m_scene;
        nau::text::TextHandle m_label;
    };
}  // namespace

int main()
{
    const int code = nau::runApplication(std::make_unique<CubeDemo>());
    return textFailed ? 1 : code;
}
