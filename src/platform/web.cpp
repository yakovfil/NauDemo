#include <emscripten.h>

#include <fstream>
#include <string_view>

#include "../demo_platform.h"
#include "nau/app/application.h"
#include "nau/app/browser_runtime.h"
#include "nau/io/asset_pack_file_system.h"
#include "nau/io/virtual_file_system.h"
#include "nau/render/browser_renderer.h"
#include "nau/serialization/json.h"
#include "nau/service/service.h"
#include "nau/service/service_provider.h"

namespace nau::demo
{
    nau::Result<std::vector<std::byte>> readPackage(const char* name)
    {
        const std::string path = std::string("/demo/") + name;
        auto file = getServiceProvider().get<io::IVirtualFileSystem>().openFile(path, io::AccessMode::Read, io::OpenFileMode::OpenExisting);
        if (!file || !file->getSize() || file->getSize() > 16 * 1024 * 1024)
            return NauMakeError("Missing, empty or oversized package input {}", path);
        std::vector<std::byte> bytes(file->getSize());
        io::IStreamReader::Ptr input = file->createStream();
        if (!input)
            return NauMakeError("Could not open package entry {}", path);
        auto read = input->read(bytes.data(), bytes.size());
        if (!read || *read != bytes.size())
            return NauMakeError("Could not read package entry {}", path);
        return bytes;
    }

    class WebPlatform final : public DemoPlatform,
                              public IServiceInitialization,
                              public IServiceShutdown,
                              public IBrowserRuntimeService
    {
        NAU_RTTI_CLASS(WebPlatform, DemoPlatform, IServiceInitialization, IServiceShutdown, IBrowserRuntimeService)
    public:
        Result<> configure() override
        {
            return {};
        }
        void initialized() override
        {
        }
        async::Task<> initService() override
        {
            co_return;
        }
        async::Task<> prepareAssets() override
        {
            co_await nextTurn();
            if (getApplication().isClosing())
                co_return;
            auto filesystem = io::openAssetPackFileSystem("/demo-package/NauDemo.nau_pack");
            if (!filesystem)
                co_await async::Task<>::makeRejected(filesystem.getError());
            co_await getServiceProvider().get<io::IVirtualFileSystem>().mount("/", *filesystem);
            for (const char* name : {"app.json", "cube.web.json"})
            {
                auto bytes = readPackage(name);
                if (!bytes)
                    co_await async::Task<>::makeRejected(bytes.getError());
                auto json = serialization::jsonParseString(std::string_view(reinterpret_cast<const char*>(bytes->data()), bytes->size()));
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
            for (const char* name : {"cube.gltf", "cube.bin", "fonts/Abel-Regular.ttf"})
            {
                auto bytes = readPackage(name);
                if (!bytes)
                    co_await async::Task<>::makeRejected(bytes.getError());
            }
        }
        void decorateScene(scene::IScene&, CubeScene&) override
        {
        }
        async::Task<> presentStartup(CubeScene& scene) override
        {
            auto geometry = scene.cube->getRootComponent<scene::StaticMeshComponent>()
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
            auto drawn = m_renderer.draw(*scene.cube, *scene.camera);
            if (!drawn)
                co_await async::Task<>::makeRejected(drawn.getError());
        }
        Result<> present(CubeScene& scene) override
        {
            return m_renderer.draw(*scene.cube, *scene.camera);
        }
        void observeStep(const CubeScene& scene, std::chrono::milliseconds dt) override
        {
            m_simulationMs += dt.count();
            MAIN_THREAD_EM_ASM({ Module.nauDemoSimulation = ({milliseconds: $0, angle: $1, elapsed: $2}); }, m_simulationMs, scene.angle, dt.count());
        }
        void reportFailure(Error::Ptr error) override
        {
            m_failure = std::move(error);
        }
        Result<> pollBrowserRuntime() override
        {
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
        async::Task<> shutdownService() override
        {
            co_await m_renderer.stop();
            m_mesh = nullptr;
        }

    private:
        async::Task<> nextTurn()
        {
            m_continue = async::TaskSource<>{};
            m_initializationPending = true;
            return m_continue.getTask();
        }
        Ptr<CpuMeshView> m_mesh;
        BrowserRenderer m_renderer;
        Error::Ptr m_failure;
        async::TaskSource<> m_continue = nullptr;
        bool m_initializationPending = false;
        int m_simulationMs = 0;
    };
    std::unique_ptr<DemoPlatform> createDemoPlatform()
    {
        return std::make_unique<WebPlatform>();
    }
}  // namespace nau::demo
