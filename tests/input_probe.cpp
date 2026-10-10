// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#include <json/json.h>

#include <cstdio>

#include "nau/app/application.h"
#include "nau/app/run_application.h"
#include "nau/input.h"
#include "nau/render/scene_backend.h"
#include "nau/scene/camera/camera_manager.h"
#include "nau/scene/packaged_scene_application.h"
#include "nau/scene/scene_manager.h"
#include "nau/service/service_provider.h"
#include "nau_project_policy.h"
#ifdef __EMSCRIPTEN__
    #include <emscripten.h>

    #include "nau/input_system.h"
#endif

namespace
{
    class InputObserver final : public nau::render::ISceneFrameObserver,
                                public nau::IRttiObject
    {
        NAU_RTTI_CLASS(InputObserver, nau::render::ISceneFrameObserver, nau::IRttiObject)
        unsigned m_frames = 0;
        void frameSubmitted(const nau::render::SceneFrame& frame) override
        {
            using namespace nau;
            auto camera = getServiceProvider().get<scene::ICameraManager>().getCameras().getWorldMainCamera();
            Json::Value record;
            record["frame"] = ++m_frames;
            record["camera"] = frame.camera;
            record["valid"] = camera && frame.camera == toString(camera->getCameraUid()) && getApplication().isMainThread();
            record["valid"] = record["valid"].asBool() &&
                              !input::isKeyboardButtonHold(99, input::Key::W) &&
                              !input::isKeyboardButtonHold(0, static_cast<input::Key>(-1)) &&
                              !input::isMouseButtonHold(0, static_cast<input::MouseKey>(-1));
            if (camera)
            {
                const auto& transform = camera->getWorldTransform();
                for (unsigned i = 0; i < 3; ++i)
                    record["position"].append(float(transform.getTranslation().getElem(i)));
                for (unsigned i = 0; i < 4; ++i)
                    record["rotation"].append(float(transform.getRotation().getElem(i)));
            }
            for (auto value : frame.viewProjection)
                record["viewProjection"].append(value);
            for (auto value : frame.drawable)
                record["drawable"].append(value);
            const input::Key keys[] = {input::Key::W, input::Key::A, input::Key::S, input::Key::D, input::Key::Q, input::Key::E};
            for (auto key : keys)
                record["held"].append(input::isKeyboardButtonHold(0, key));
            record["drag"] = input::isMouseButtonHold(0, input::MouseKey::ButtonLeft);
            for (int button = 0; button < 5; ++button)
                record["buttons"].append(input::isMouseButtonHold(0, static_cast<input::MouseKey>(button)));
            record["delta"].append(input::getMouseAxisDelta(0, input::MouseKey::AxisX));
            record["delta"].append(input::getMouseAxisDelta(0, input::MouseKey::AxisY));
            Json::StreamWriterBuilder writer;
            writer["indentation"] = "";
            const auto text = Json::writeString(writer, record);
            std::printf("INPUT_PROBE %s\n", text.c_str());
            std::fflush(stdout);
#ifdef __EMSCRIPTEN__
            MAIN_THREAD_EM_ASM({ Module.inputProbe = JSON.parse(UTF8ToString($0)); }, text.c_str());
#endif
        }
    };

    class InputProbe final : public nau::ApplicationDelegate
    {
        Ptr m_application;

    public:
        explicit InputProbe(Ptr application) :
            m_application(std::move(application))
        {
        }

    private:
        nau::Result<> configureApplication() override
        {
            return m_application->configureApplication();
        }
        std::string getModulesListString() const override
        {
            return m_application->getModulesListString();
        }
        nau::Result<> initializeServices() override
        {
            NauCheckResult(m_application->initializeServices());
            nau::getServiceProvider().addService(std::make_unique<InputObserver>());
            return {};
        }
        void onApplicationInitialized() override
        {
            m_application->onApplicationInitialized();
        }
        nau::async::Task<> startupApplication() override
        {
            co_await m_application->startupApplication();
#ifdef __EMSCRIPTEN__
            if (nau::input::getGaInputManager() || nau::getServiceProvider().get<nau::IInputSystem>().getController("keyboard"))
                co_await nau::async::Task<>::makeRejected(NauMakeError("Unsupported browser input API appeared available"));
#endif
            if (!nau::getApplication().isClosing())
                nau::getServiceProvider().get<nau::scene::ISceneManager>().getDefaultWorld().setSimulationPause(true);
        }
        void onApplicationPreUpdate(std::chrono::milliseconds dt) override
        {
            m_application->onApplicationPreUpdate(dt);
        }
        void onApplicationPostUpdate(std::chrono::milliseconds dt) override
        {
            m_application->onApplicationPostUpdate(dt);
        }
    };
}  // namespace

int main()
{
    nau::scene::PackagedSceneOptions options;
    options.configurationPath = nau::project::StartupConfiguration;
    options.supportedComponents = nau::project::SupportedComponents;
    options.runtimeProfile = nau::project::RuntimeProfile;
    options.renderingConfiguration = nau::project::RenderingConfiguration;
    return nau::runApplication(std::make_unique<InputProbe>(nau::scene::createPackagedSceneApplication(std::move(options))));
}
