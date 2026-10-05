#include "demo_application.h"

#include "demo_platform.h"
#include "demo_text.h"
#include "nau/app/application.h"
#include "nau/module/module_manager.h"
#include "nau/scene/camera/camera_manager.h"
#include "nau/scene/scene_manager.h"

namespace nau::demo
{
    namespace
    {
        bool failed = false;
        class DemoApplication final : public ApplicationDelegate
        {
        public:
            DemoApplication() :
                m_platform(createDemoPlatform()),
                m_adapter(m_platform.get())
            {
            }
            Result<> configureApplication() override
            {
                return m_adapter->configure();
            }
            std::string getModulesListString() const override
            {
                return NAU_MODULES_LIST;
            }
            Result<> initializeServices() override
            {
                getServiceProvider().addService(std::move(m_platform));
                getServiceProvider().addService<text::ScreenText>();
                return {};
            }
            void onApplicationInitialized() override
            {
                m_adapter->initialized();
            }
            async::Task<> startupApplication() override
            {
                co_await m_adapter->prepareAssets();
                if (getApplication().isClosing())
                    co_return;
                auto label = createDemoText();
                if (!label)
                    co_await async::Task<>::makeRejected(label.getError());
                m_label = *label;
                auto& factory = getServiceProvider().get<scene::ISceneFactory>();
                auto scene = factory.createEmptyScene();
                m_scene = createCubeScene(factory, *scene);
                m_adapter->decorateScene(*scene, m_scene);
                co_await getServiceProvider().get<scene::ISceneManager>().activateScene(std::move(scene));
                if (getApplication().isClosing())
                    co_return;
                getServiceProvider().get<scene::ICameraManager>().setMainCamera(
                    m_scene.camera->getRootComponent<scene::CameraComponent>());
                co_await drawDemoText(m_label);
                co_await m_adapter->presentStartup(m_scene);
                NAU_LOG_DEBUG("NauDemo text ready");
            }
            void onApplicationPreUpdate(std::chrono::milliseconds dt) override
            {
                const auto elapsed = std::getenv("NAU_DEMO_FREEZE") ? std::chrono::milliseconds(0) : dt;
                m_scene.advance(elapsed);
                auto drawn = drawDemoText(m_label);
                if (!drawn)
                    fail(drawn.getError());
                m_adapter->observeStep(m_scene, elapsed);
            }
            void onApplicationPostUpdate(std::chrono::milliseconds) override
            {
                auto result = m_adapter->present(m_scene);
                if (!result)
                    fail(result.getError());
            }

        private:
            void fail(Error::Ptr error)
            {
                failed = true;
                NAU_LOG_ERROR("NauDemo failed: {}", error->getMessage());
                m_adapter->reportFailure(error);
                getApplication().stop();
            }
            std::unique_ptr<DemoPlatform> m_platform;
            DemoPlatform* m_adapter;
            CubeScene m_scene;
            text::TextHandle m_label;
        };
    }  // namespace
    ApplicationDelegate::Ptr createDemoApplication()
    {
        return std::make_unique<DemoApplication>();
    }
    bool demoFailed()
    {
        return failed;
    }
}  // namespace nau::demo
