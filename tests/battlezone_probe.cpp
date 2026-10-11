#include <json/json.h>

#include <cstdio>
#include <limits>

#include "battlezone.h"
#include "nau/app/application.h"
#include "nau/app/run_application.h"
#include "nau/input.h"
#include "nau/scene/packaged_scene_application.h"
#include "nau/scene/scene_manager.h"
#include "nau/service/service_provider.h"
#include "nau_project_policy.h"
#ifdef __EMSCRIPTEN__
    #include <emscripten.h>
    #include <emscripten/html5.h>
#endif
using namespace nau;
namespace
{
    std::string mode;
    class FaultBackend final : public render::SceneBackend
    {
        std::unique_ptr<render::SceneBackend> m_backend = render::createSceneBackend();

    public:
        Result<> initialize(void* window) override
        {
            NauCheckResult(m_backend->initialize(window));
            if (mode == "init-error")
                return NauMakeError("Injected vector backend initialization failure");
            if (mode == "stop-startup")
            {
                getApplication().stop();
                getApplication().stop();
            }
            return {};
        }
        Result<render::SceneDrawable> poll() override
        {
            return m_backend->poll();
        }
        Result<> submit(const render::SceneFrame& frame) override
        {
            NauCheckResult(m_backend->submit(frame));
            if (mode == "submit-error")
                return NauMakeError("Injected vector backend failure after buffer upload");
            return {};
        }
        Result<> stop() override
        {
            return m_backend->stop();
        }
    };
    class BackendFactory final : public render::ISceneBackendFactory,
                                 public IRttiObject
    {
        NAU_RTTI_CLASS(BackendFactory, render::ISceneBackendFactory, IRttiObject)
        std::unique_ptr<render::SceneBackend> createBackend() override
        {
            if (mode == "shader-error" || mode == "upload-error")
            {
                auto backend = render::createSceneBackend();
                backend->injectTestFailure(mode == "shader-error" ? render::SceneBackend::TestFailure::VectorShader : render::SceneBackend::TestFailure::VectorUpload);
                return backend;
            }
            return std::make_unique<FaultBackend>();
        }
    };
    DemoBattlezone* game()
    {
        DemoBattlezone* result = nullptr;
        for (auto s : getServiceProvider().get<scene::ISceneManager>().getDefaultWorld().getScenes())
            if (s)
                s->getRoot().walkComponents([](scene::Component& c, void* p)
                {
                    if (auto* g = c.as<DemoBattlezone*>())
                        *static_cast<DemoBattlezone**>(p) = g;
                    return true;
                }, &result, true);
        return result;
    }
    class Observer final : public render::ISceneFrameObserver,
                           public IRttiObject
    {
        NAU_RTTI_CLASS(Observer, render::ISceneFrameObserver, IRttiObject)
        unsigned count = 0;
        void frameSubmitted(const render::SceneFrame& f) override
        {
            auto* g = game();
            const demo::battlezone::Simulation empty;
            const auto& s = g ? g->simulation() : empty;
            const auto a = getServiceProvider().get<audio::IPortableAudio>().statistics();
            Json::Value r;
            r["frame"] = ++count;
            r["score"] = s.score;
            r["lives"] = s.lives;
            r["x"] = s.player.x;
            r["z"] = s.player.z;
            r["heading"] = s.heading;
            r["enemyDestroyed"] = s.enemyDestroyed;
            r["projectiles"] = unsigned(s.projectiles.size());
            r["fragments"] = unsigned(s.fragments.size());
            r["requests"] = Json::UInt64(a.requests);
            r["started"] = Json::UInt64(a.started);
            r["nonzeroFrames"] = Json::UInt64(a.nonzeroFrames);
            r["active"] = a.active;
            r["pending"] = a.pending;
            r["focused"] = input::isKeyboardButtonHold(0, input::Key::Focus);
            r["vectors"] = unsigned(f.vectors.size());
            Json::StreamWriterBuilder b;
            b["indentation"] = "";
            const auto value = Json::writeString(b, r);
            std::printf("BATTLEZONE_PROBE %s\n", value.c_str());
            std::fflush(stdout);
#ifdef __EMSCRIPTEN__
            MAIN_THREAD_EM_ASM({ Module.battlezoneProbe = JSON.parse(UTF8ToString($0)); }, value.c_str());
#endif
        }
    };
    class Probe final : public ApplicationDelegate
    {
        Ptr m_inner;
        std::string m_mode;
        unsigned m_updates = 0;

    public:
        Probe(Ptr inner, std::string mode) :
            m_inner(std::move(inner)),
            m_mode(std::move(mode))
        {
        }
        Result<> configureApplication() override
        {
            return m_inner->configureApplication();
        }
        std::string getModulesListString() const override
        {
            return m_inner->getModulesListString();
        }
        Result<> initializeServices() override
        {
            NauCheckResult(m_inner->initializeServices());
            getServiceProvider().addService(std::make_unique<Observer>());
            if (m_mode == "init-error" || m_mode == "submit-error" || m_mode == "stop-startup" || m_mode == "shader-error" || m_mode == "upload-error")
                getServiceProvider().addService(std::make_unique<BackendFactory>());
            return {};
        }
        void onApplicationInitialized() override
        {
            m_inner->onApplicationInitialized();
        }
        async::Task<> startupApplication() override
        {
            co_await m_inner->startupApplication();
            if (auto* g = game())
            {
                auto& s = g->acceptanceState();
                if (m_mode == "last-life")
                {
                    s.lives = 1;
                    s.protection = 0;
                    s.enemy = {0, -18};
                }
                if (m_mode == "invalid-vector")
                    s.enemy.x = std::numeric_limits<float>::infinity();
                if (m_mode == "capacity")
                    s.projectiles.resize(render::VectorPresentation::WorldLimit + 1);
                if (m_mode == "remove")
                    g->destroy();
                if (m_mode == "stop")
                {
                    getApplication().stop();
                    getApplication().stop();
                }
            }
        }
        void onApplicationPreUpdate(std::chrono::milliseconds dt) override
        {
            m_inner->onApplicationPreUpdate(dt);
        }
        void onApplicationPostUpdate(std::chrono::milliseconds dt) override
        {
            m_inner->onApplicationPostUpdate(dt);
            ++m_updates;
            if (m_mode == "remove" && m_updates == 8)
                getApplication().stop();
#ifdef __EMSCRIPTEN__
            if (m_mode == "context-loss" && m_updates == 4)
                EM_ASM({ GL.currentContext.GLctx.getExtension('WEBGL_lose_context').loseContext(); });
#endif
        }
    };
}  // namespace
int main(int argc, char** argv)
{
    mode = argc > 1 ? argv[1] : "normal";
    scene::PackagedSceneOptions o;
    o.configurationPath = project::StartupConfiguration;
    o.supportedComponents = project::SupportedComponents;
    o.runtimeProfile = project::RuntimeProfile;
    o.renderingConfiguration = project::RenderingConfiguration;
    return runApplication(std::make_unique<Probe>(scene::createPackagedSceneApplication(std::move(o)), argc > 1 ? argv[1] : "normal"));
}
