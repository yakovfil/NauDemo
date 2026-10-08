// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.

#include <algorithm>
#include <cstdio>

#include "nau/app/application.h"
#include "nau/app/global_properties.h"
#include "nau/app/run_application.h"
#include "nau/assets/asset_container.h"
#include "nau/assets/asset_manager.h"
#include "nau/diag/logging.h"
#include "nau/io/file_system.h"
#include "nau/io/memory_stream.h"
#include "nau/rtti/rtti_impl.h"
#include "nau/scene/components/component_life_cycle.h"
#include "nau/scene/components/internal/missing_component.h"
#include "nau/scene/packaged_scene_application.h"
#include "nau/scene/scene_factory.h"
#include "nau/scene/scene_manager.h"
#include "nau/serialization/json.h"
#include "nau/serialization/native_runtime_value/native_value_base.h"
#include "nau/service/service_provider.h"
#ifdef NAU_PACKAGED_PROJECT_TEST
    #include "nau_project_policy.h"
#endif
#ifdef __EMSCRIPTEN__
    #include <emscripten.h>

    #include "nau/app/browser_runtime.h"
#endif

namespace
{
    bool delayStartup = false;
    std::string nativeStopPhase;
    std::string legacyScene;

    class StartupGateComponent final : public nau::scene::Component,
                                       public nau::scene::IComponentActivation
    {
        NAU_OBJECT(StartupGateComponent, nau::scene::Component, nau::scene::IComponentActivation)
        NAU_DECLARE_DYNAMIC_OBJECT
        NAU_CLASS_FIELDS(CLASS_FIELD(failActivation), CLASS_FIELD(immediateFailure))
        bool failActivation = false;
        bool immediateFailure = false;

        nau::async::Task<> activateComponentAsync() override
        {
            if (immediateFailure)
                co_await nau::async::Task<>::makeRejected(NauMakeError("Probe immediate activation failure"));
#ifdef __EMSCRIPTEN__
            MAIN_THREAD_EM_ASM({ Module.sceneProbePhase = 'activation'; });
#else
            if (nativeStopPhase == "activation")
            {
                std::puts("PROBE_STOP activation");
                nau::getApplication().stop();
                nau::getApplication().stop();
            }
#endif
            co_await std::chrono::milliseconds(250);
            if (failActivation)
                co_await nau::async::Task<>::makeRejected(NauMakeError("Probe deferred activation failure"));
#ifdef __EMSCRIPTEN__
            MAIN_THREAD_EM_ASM({ Module.sceneProbeActivationSettled = true; });
#else
            std::puts("PROBE_ACTIVATION_SETTLED");
#endif
        }
    };
    NAU_IMPLEMENT_DYNAMIC_OBJECT(StartupGateComponent)

#ifdef __EMSCRIPTEN__
    class LoadObserver final : public nau::IBrowserRuntimeService,
                               public nau::IRttiObject
    {
        NAU_RTTI_CLASS(LoadObserver, nau::IBrowserRuntimeService, nau::IRttiObject)
        nau::Result<> pollBrowserRuntime() override
        {
            auto* properties = nau::getServiceProvider().find<nau::GlobalProperties>();
            const auto path = properties ? properties->getValue<std::string>("scene/startupScene") : std::nullopt;
            if (path && !m_reported)
            {
                auto& assets = nau::getServiceProvider().get<nau::IAssetManager>();
                auto resolved = assets.resolvePath(nau::AssetPath{*path});
                auto descriptor = resolved ? assets.findAsset(*resolved) : nullptr;
                if (descriptor && descriptor->getLoadState() == nau::IAssetDescriptor::LoadState::InProgress)
                {
                    m_reported = true;
                    MAIN_THREAD_EM_ASM({ Module.sceneProbePhase = 'load'; });
                }
            }
            return nau::ResultSuccess;
        }
        bool m_reported = false;
    };
#endif
    // This consumer observes production scene state. It is not linked into the
    // delivered project application and cannot substitute page-side objects.
    class ProbeDelegate final : public nau::ApplicationDelegate
    {
    public:
        explicit ProbeDelegate(Ptr application) :
            m_application(std::move(application))
        {
        }

        ~ProbeDelegate()
        {
            const bool clean = !nau::applicationExists() && !nau::hasServiceProvider();
            std::printf("PROBE_CLEANUP %s\n", clean ? "true" : "false");
#ifdef __EMSCRIPTEN__
            MAIN_THREAD_EM_ASM({ Module.sceneProbeCleanup = !!$0; }, clean);
#endif
        }

    private:
        nau::Result<> configureApplication() override
        {
            NAU_LOG_INFO("PROBE_LOG info");
            NAU_LOG_WARNING("PROBE_LOG warning");
            NAU_LOG_ERROR("PROBE_LOG error");
            NAU_LOG_CRITICAL("PROBE_LOG critical");
            return m_application->configureApplication();
        }
        std::string getModulesListString() const override
        {
            return m_application->getModulesListString();
        }
        nau::Result<> initializeServices() override
        {
            using Guard = nau::ser_detail::ParentMutabilityGuard;
            using Storage = nau::rtti_detail::RttiClassStorage<typename Guard::ClassPolicy::RC>;
            static_assert(alignof(nau::rtti::InstanceInplaceStorage<Guard>) >= alignof(typename Storage::SharedState));
            // Exercise the alignment even when embedded after a narrow field.
            struct Embedded
            {
                uint32_t prefix = 0;
                nau::rtti::InstanceInplaceStorage<Guard> storage;
            } embedded;
            auto parent = nau::serialization::jsonCreateDictionary();
            auto guard = nau::rtti::createInstanceInplace<Guard>(embedded.storage, parent);
            if (!guard || guard->getParent().get() != parent->as<nau::RuntimeValue*>())
                return NauMakeError("In-place reflection guard regression");
            nau::getServiceProvider().addClass<StartupGateComponent>();
#ifdef __EMSCRIPTEN__
            nau::getServiceProvider().addService(std::make_unique<LoadObserver>());
#endif
            return m_application->initializeServices();
        }
        void onApplicationInitialized() override
        {
            m_application->onApplicationInitialized();
        }
        nau::async::Task<> startupApplication() override
        {
#ifndef __EMSCRIPTEN__
            // The strict browser profile must not remove the native factory's
            // opaque missing-component fallback or its saved type identity.
            nau::ComponentAsset original;
            original.setComponentType(nau::rtti::makeTypeInfoFromName("FutureNativeComponent"));
            original.componentTypeName = "FutureNativeComponent";
            original.uid = nau::Uid::generate();
            original.properties = *nau::serialization::jsonParseString("{\"futureProperty\":\"preserved\"}");
            const auto type = original.getComponentType();
            auto object = nau::getServiceProvider().get<nau::scene::ISceneFactory>().createSceneObject(&type);
            auto* missing = object->getRootComponent().as<nau::scene::IMissingComponent*>();
            if (!missing)
                co_await nau::async::Task<>::makeRejected(NauMakeError("Native missing-component fallback unavailable"));
            missing->setComponentData(original);
            nau::ComponentAsset restored;
            missing->fillComponentData(restored);
            auto dictionary = restored.properties->as<nau::RuntimeReadonlyDictionary*>();
            auto value = dictionary->getValue("futureProperty");
            auto text = value->as<nau::RuntimeStringValue*>();
            if (restored.componentTypeId != original.componentTypeId || restored.componentTypeName != original.componentTypeName ||
                restored.uid != original.uid || text->getString() != "preserved")
                co_await nau::async::Task<>::makeRejected(NauMakeError("Native missing-component data was not preserved: type {} / {}, names {} / {}, uid {} / {}, property {}",
                                                                       restored.componentTypeId, original.componentTypeId, restored.componentTypeName, original.componentTypeName,
                                                                       toString(restored.uid), toString(original.uid), text->getString()));
#endif
            if (delayStartup)
            {
#ifdef __EMSCRIPTEN__
                MAIN_THREAD_EM_ASM({ Module.sceneProbePhase = 'before-mount'; });
#else
                if (nativeStopPhase == "before-mount")
                {
                    std::puts("PROBE_STOP before-mount");
                    nau::getApplication().stop();
                    nau::getApplication().stop();
                }
#endif
                co_await std::chrono::milliseconds(250);
            }
            if (nau::getApplication().isClosing())
                co_return;
#ifndef __EMSCRIPTEN__
            if (!legacyScene.empty())
            {
                nau::io::IStreamReader::Ptr stream = nau::io::createNativeFileStream(
                    legacyScene.c_str(), nau::io::AccessMode::Read, nau::io::OpenFileMode::OpenExisting);
                auto loaders = nau::getServiceProvider().getAll<nau::IAssetContainerLoader>();
                if (!stream || loaders.empty())
                    co_await nau::async::Task<>::makeRejected(NauMakeError("Legacy reader input unavailable"));
                auto container = co_await loaders.front()->loadFromStream(stream, {"nscene", {}, nullptr});
                auto raw = container->getAsset("");
                auto scene = nau::getServiceProvider().get<nau::scene::ISceneFactory>().createSceneFromAsset(raw->as<nau::SceneAsset&>());
                co_await nau::getServiceProvider().get<nau::scene::ISceneManager>().activateScene(std::move(scene));
            }
            else
#endif
                co_await m_application->startupApplication();
            if (!nau::getApplication().isClosing())
                snapshot("initial");
        }
        void onApplicationPostUpdate(std::chrono::milliseconds dt) override
        {
            m_application->onApplicationPostUpdate(dt);
            if (++m_updates == 10)
            {
                snapshot("updated");
#ifndef __EMSCRIPTEN__
                nau::getApplication().stop();
#endif
            }
        }

        void snapshot(const char* phase)
        {
            using namespace nau;
            Json::Value objects{Json::arrayValue};
            const auto scenes = getServiceProvider().get<scene::ISceneManager>().getActiveScenes();
            for (const auto& active : scenes)
            {
                auto add = [&](scene::SceneObject& object)
                {
                    Json::Value value;
                    value["uid"] = toString(object.getUid());
                    value["name"] = std::string(object.getName());
                    value["parent"] = object.getParentObject() ? toString(object.getParentObject()->getUid()) : "";
                    const auto transform = object.getTransform();
                    serialization::runtimeApplyToJsonValue(value["transform"], makeValueRef(transform)).ignore();
                    Json::Value components{Json::arrayValue};
                    for (auto* component : object.getDirectComponents())
                    {
                        Json::Value entry;
                        entry["uid"] = toString(component->getUid());
                        entry["type"] = std::string(component->getClassDescriptor()->getClassTypeInfo().getTypeName());
                        serialization::runtimeApplyToJsonValue(entry["properties"], nau::Ptr{component->as<RuntimeValue*>()}).ignore();
                        components.append(std::move(entry));
                    }
                    value["components"] = std::move(components);
                    objects.append(std::move(value));
                };
                add(active->getRoot());
                for (auto* object : active->getRoot().getAllChildObjects())
                    add(*object);
            }
            Json::Value result;
            result["phase"] = phase;
            result["updates"] = m_updates;
            result["objects"] = std::move(objects);
            Json::StreamWriterBuilder writer;
            writer["indentation"] = "";
            const std::string json = Json::writeString(writer, result);
            std::printf("PROBE_SCENE %s\n", json.c_str());
#ifdef __EMSCRIPTEN__
            MAIN_THREAD_EM_ASM({ Module.sceneProbe ??= {}; Module.sceneProbe[UTF8ToString($0)] = JSON.parse(UTF8ToString($1)); }, phase, json.c_str());
#endif
        }

        Ptr m_application;
        unsigned m_updates = 0;
    };
}  // namespace

int main(int argc, char** argv)
{
    nau::scene::PackagedSceneOptions options;
#ifdef __EMSCRIPTEN__
    options.archivePath = "/project-package/content.nau_pack";
    if (argc >= 2)
        options.configurationPath = argv[1];
    delayStartup = argc > 2 && std::string_view(argv[2]) == "delay-startup";
#else
    if (argc < 2)
        return 2;
    options.archivePath = argv[1];
    if (argc > 2)
        options.configurationPath = argv[2];
    if (argc > 3)
    {
        const std::string_view argument = argv[3];
        if (argument.starts_with("stop:"))
        {
            nativeStopPhase = argument.substr(5);
            delayStartup = nativeStopPhase == "before-mount";
        }
        else
        {
            legacyScene = argument;
        }
    }
#endif
#ifdef NAU_PACKAGED_PROJECT_TEST
    options.supportedComponents = nau::project::SupportedComponents;
    options.supportedComponents.push_back("StartupGateComponent");
#else
    options.supportedComponents = {"nau::scene::SceneComponent", "nau::scene::CameraComponent",
                                   "nau::scene::StaticMeshComponent", "MyMover", "MyRotator", "StartupGateComponent"};
#endif
    return nau::runApplication(std::make_unique<ProbeDelegate>(nau::scene::createPackagedSceneApplication(std::move(options))));
}
