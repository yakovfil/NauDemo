#include <emscripten.h>

#include <fstream>

#include "demo_scene.h"
#include "nau/app/application_services.h"
#include "nau/app/browser_runtime.h"
#include "nau/app/main_loop/game_system.h"
#include "nau/io/virtual_file_system.h"
#include "nau/module/module_manager.h"
#include "nau/render/browser_renderer.h"
#include "nau/scene/camera/camera_manager.h"
#include "nau/scene/scene_manager.h"
#include "nau/serialization/json.h"
#ifdef NAU_DEMO_TEST_HOOKS
    #include "web_test_hooks.h"
#endif
#include "nau/service/service.h"
#include "nau/service/service_provider.h"

namespace
{
    nau::Result<std::vector<std::byte>> readPackage(const char* name)
    {
        const std::string path = std::string("/demo-package/") + name;
        std::ifstream input(path, std::ios::binary | std::ios::ate);
        if (!input || input.tellg() <= 0 || input.tellg() > 16 * 1024 * 1024)
            return NauMakeError("Missing, empty or oversized package input {}",
                                path.c_str());
        std::vector<std::byte> bytes(static_cast<size_t>(input.tellg()));
        input.seekg(0);
        if (!input.read(reinterpret_cast<char*>(bytes.data()), bytes.size()))
            return NauMakeError("Could not read package input {}", path.c_str());
        return bytes;
    }

    class DemoService final : public nau::IServiceInitialization,
                              public nau::IServiceShutdown,
                              public nau::IGamePreUpdate,
                              public nau::IGamePostUpdate,
                              public nau::IBrowserRuntimeService
    {
        NAU_RTTI_CLASS(DemoService, nau::IServiceInitialization, nau::IServiceShutdown, nau::IGamePreUpdate, nau::IGamePostUpdate, nau::IBrowserRuntimeService)
    public:
        nau::async::Task<> initService() override
        {
            using namespace nau;
            // Separate owner-loop turns let Stop settle startup before reading
            // assets or allocating graphics, without blocking the worker.
            m_continue = async::TaskSource<>{};
            m_initializationPending = true;
            MAIN_THREAD_EM_ASM({ Module.nauDemoStage = 'assets'; });
            co_await m_continue.getTask();
            if (getApplication().isClosing())
                co_return;
            for (const char* name : {"app.json", "cube.web.json"})
            {
                auto bytes = readPackage(name);
                if (!bytes)
                    co_await async::Task<>::makeRejected(bytes.getError());
                auto json = serialization::jsonParseString(eastl::string_view(reinterpret_cast<const char*>(bytes->data()), bytes->size()));
                if (!json)
                    co_await async::Task<>::makeRejected(NauMakeError("Invalid package JSON {}", name));
                auto* dictionary = *json ? (*json)->as<RuntimeReadonlyDictionary*>() : nullptr;
                if (!dictionary)
                    co_await async::Task<>::makeRejected(NauMakeError("Package JSON must be an object: {}", name));
                if (dictionary->getSize() != (std::string_view(name) == "app.json" ? 2 : 3))
                    co_await async::Task<>::makeRejected(NauMakeError("Unsupported fields in {}", name));
                const auto require = [dictionary, name](const char* key, const char* expected) -> Result<>
                {
                    auto value = dictionary->getValue(key);
                    auto* text = value ? value->as<RuntimeStringValue*>() : nullptr;
                    if (!text || text->getString() != expected)
                        return NauMakeError("Unsupported {} in {} (expected {})", key, name, expected);
                    return {};
                };
                if (std::string_view(name) == "app.json")
                {
                    co_await require("mesh", "cube.gltf");
                    co_await require("material", "cube.web.json");
                }
                else
                {
                    co_await require("type", "blue-diffuse");
                    co_await require("vertexShader", "cube.vert");
                    co_await require("fragmentShader", "cube.frag");
                }
            }
            std::vector<CpuAssetFile> files;
            for (const char* name : {"cube.gltf", "cube.bin"})
            {
                auto bytes = readPackage(name);
                if (!bytes)
                    co_await async::Task<>::makeRejected(bytes.getError());
                files.push_back({name, std::move(*bytes)});
            }
            auto filesystem = createCpuAssetFileSystem(std::move(files));
            if (!filesystem)
                co_await async::Task<>::makeRejected(filesystem.getError());
            auto mounted = getServiceProvider().get<io::IVirtualFileSystem>().mount(
                "/demo", *filesystem);
            if (!mounted)
                co_await async::Task<>::makeRejected(mounted.getError());
            auto& factory = getServiceProvider().get<scene::ISceneFactory>();
            auto scene = factory.createEmptyScene();
            m_scene = demo::createCubeScene(factory, *scene);
#ifdef NAU_DEMO_TEST_HOOKS
            if (MAIN_THREAD_EM_ASM_INT({ return !!Module.nauDemoPendingTest; }))
                m_scene.cube->addComponent<demo::test::PendingComponent>().state = &m_pending;
#endif
            co_await getServiceProvider().get<scene::ISceneManager>().activateScene(
                std::move(scene));
            if (getApplication().isClosing())
                co_return;
            getServiceProvider().get<scene::ICameraManager>().setMainCamera(
                m_scene.camera->getRootComponent<scene::CameraComponent>());
            auto geometry = m_scene.cube->getRootComponent<scene::StaticMeshComponent>()
                                .getMeshGeometry();
            auto loaded = co_await geometry.getAssetViewTyped<CpuMeshView>().doTry();
            if (!loaded)
                co_await async::Task<>::makeRejected(loaded.getError());
            if (!*loaded)
                co_await async::Task<>::makeRejected(
                    NauMakeError("Cube CPU asset view unavailable"));
            m_mesh = *loaded;
            m_continue = async::TaskSource<>{};
            m_initializationPending = true;
            MAIN_THREAD_EM_ASM({ Module.nauDemoStage = 'graphics'; });
            co_await m_continue.getTask();
            if (getApplication().isClosing())
                co_return;
            auto vertex = readPackage("cube.vert"), fragment = readPackage("cube.frag");
            if (!vertex)
                co_await async::Task<>::makeRejected(vertex.getError());
            if (!fragment)
                co_await async::Task<>::makeRejected(fragment.getError());
            auto initialized = m_renderer.initialize(
                *m_mesh,
                {reinterpret_cast<const char*>(vertex->data()), vertex->size()},
                {reinterpret_cast<const char*>(fragment->data()), fragment->size()});
            if (!initialized)
                co_await async::Task<>::makeRejected(initialized.getError());
            auto drawn = m_renderer.draw(*m_scene.cube, *m_scene.camera);
            if (!drawn)
                co_await async::Task<>::makeRejected(drawn.getError());
            MAIN_THREAD_EM_ASM({ Module.nauDemoStage = 'ready'; });
        }
        void gamePreUpdate(std::chrono::milliseconds dt) override
        {
            m_scene.advance(dt);
            m_simulationMs += dt.count();
            MAIN_THREAD_EM_ASM({ Module.nauDemoSimulation = ({milliseconds: $0, angle: $1, elapsed: $2}); }, m_simulationMs, m_scene.angle, dt.count());
        }
        void gamePostUpdate(std::chrono::milliseconds) override
        {
            if (m_failure)
                return;
            auto result = m_renderer.draw(*m_scene.cube, *m_scene.camera);
            if (!result)
                m_failure = result.getError();
        }
        nau::Result<> pollBrowserRuntime() override
        {
#ifdef NAU_DEMO_TEST_HOOKS
            if (m_scene.camera && MAIN_THREAD_EM_ASM_INT({ return !!Module.nauDemoMoveCamera; }))
            {
                m_scene.camera->setTranslation({2.0f, 3.0f, 9.0f});
                m_scene.camera->getRootComponent<nau::scene::CameraComponent>().setFov(60.0f);
            }
            if (m_pending.pending && !m_pending.released && MAIN_THREAD_EM_ASM_INT({ return !!Module.nauDemoReleasePending; }))
            {
                m_pending.released = true;
                m_pending.release.resolve();
            }
            MAIN_THREAD_EM_ASM({ Module.nauDemoPending = ({pending: !!$0, deactivated: $1, destroyed: $2}); },
                               m_pending.pending, m_pending.deactivated, m_pending.destroyed);
#endif
            if (m_initializationPending)
            {
                m_initializationPending = false;
                auto continuation = std::move(m_continue);
                continuation.resolve();
            }
            if (m_failure)
                return m_failure;
            return m_renderer.poll();
        }
        nau::async::Task<> shutdownService() override
        {
            co_await m_renderer.stop();
            m_mesh = nullptr;
            co_return;
        }

    private:
        nau::demo::CubeScene m_scene;
        nau::Ptr<nau::CpuMeshView> m_mesh;
        nau::BrowserRenderer m_renderer;
        nau::Error::Ptr m_failure;
        nau::async::TaskSource<> m_continue = nullptr;
        bool m_initializationPending = false;
        int m_simulationMs = 0;
#ifdef NAU_DEMO_TEST_HOOKS
        nau::demo::test::PendingState m_pending;
#endif
    };

    class DemoDelegate final : public nau::ApplicationInitDelegate
    {
        nau::Result<> configureApplication() override
        {
            return {};
        }
        nau::Result<> initializeApplication() override
        {
            NauCheckResult(nau::loadModulesList(NAU_MODULES_LIST));
#ifdef NAU_DEMO_TEST_HOOKS
            nau::getServiceProvider().addClass<nau::demo::test::PendingComponent>();
#endif
            nau::getServiceProvider().addService(nau::createPlatformWindowService());
            nau::getServiceProvider().addService<DemoService>();
            return {};
        }
    };
}  // namespace

int main()
{
    static DemoDelegate delegate;
    return nau::runBrowserApplication(delegate,
                                      {.cooperativePresentation = true});
}
