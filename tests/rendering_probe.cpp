// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#include <json/json.h>

#include <bit>
#include <cmath>
#include <cstdio>
#include <map>
#include <string>

#include "nau/app/application.h"
#include "nau/app/application_lifecycle.h"
#include "nau/app/run_application.h"
#include "nau/assets/asset_container.h"
#include "nau/render/scene_backend.h"
#include "nau/scene/camera/camera_manager.h"
#include "nau/scene/components/billboard_component.h"
#include "nau/scene/components/camera_component.h"
#include "nau/scene/components/component_life_cycle.h"
#include "nau/scene/components/static_mesh_component.h"
#include "nau/scene/internal/scene_manager_internal.h"
#include "nau/scene/packaged_scene_application.h"
#include "nau/scene/packaged_scene_presenter.h"
#include "nau/scene/scene_factory.h"
#include "nau/scene/scene_manager.h"
#include "nau/serialization/json_utils.h"
#include "nau/service/service.h"
#include "nau/service/service_provider.h"
#include "nau_project_policy.h"
#ifdef __EMSCRIPTEN__
    #include <emscripten.h>
    #include <emscripten/html5.h>

    #include "nau/render/browser_renderer.h"
    #include "nau_scene_shaders.h"
#endif

using namespace nau;
namespace
{
    std::string mode = "normal", stage = "initial";
    unsigned updates = 0, frames = 0;
    bool frozen = false, loadAccepted = false, loadSettled = false;
    Json::Value records{Json::objectValue};
    bool motionPending = false;
    class PendingMotion final : public scene::Component,
                                public scene::IComponentAsyncUpdate
    {
        NAU_OBJECT(PendingMotion, scene::Component, scene::IComponentAsyncUpdate)
        NAU_DECLARE_DYNAMIC_OBJECT
    public:
        async::Task<> updateComponentAsync(float) override
        {
            motionPending = true;
            auto translation = getParentObject().getTranslation();
            getParentObject().setTranslation(translation + math::Vector3(0, .1f, 0));
            co_await std::chrono::milliseconds(10);
            getParentObject().setTranslation(translation + math::Vector3(0, .01f, 0));
            motionPending = false;
        }
    };
    NAU_IMPLEMENT_DYNAMIC_OBJECT(PendingMotion)
    std::string encode(const Json::Value& value)
    {
        Json::StreamWriterBuilder builder;
        builder["indentation"] = "";
        return Json::writeString(builder, value);
    }
    template <class Values>
    Json::Value array(const Values& values)
    {
        Json::Value result{Json::arrayValue};
        for (auto value : values)
            result.append(value);
        return result;
    }
    render::MatrixValues copyMatrix(const math::Matrix4& matrix)
    {
        render::MatrixValues result;
        for (unsigned column = 0; column < 4; ++column)
        {
            const auto values = matrix.getCol(column);
            for (unsigned row = 0; row < 4; ++row)
                result[column * 4 + row] = float(values.getElem(row));
        }
        return result;
    }
    void publish(const Json::Value& value)
    {
        auto text = encode(value);
        std::printf("RENDER_PROBE %s\n", text.c_str());
        std::fflush(stdout);
#ifdef __EMSCRIPTEN__
        MAIN_THREAD_EM_ASM({ Module.renderProbe = JSON.parse(UTF8ToString($0)); }, text.c_str());
#endif
    }
    scene::SceneObject* object(std::string_view name)
    {
        for (auto active : getServiceProvider().get<scene::ISceneManager>().getActiveScenes())
            if (active)
                for (auto* candidate : active->getRoot().getAllChildObjects())
                    if (candidate->getName() == name)
                        return candidate;
        return nullptr;
    }
    scene::BillboardComponent* marker()
    {
        auto uid = Uid::parseString("22222222-3333-4444-5555-666666666691");
        auto* component = getServiceProvider().get<scene::ISceneManagerInternal>().findComponent(*uid);
        return component ? component->as<scene::BillboardComponent*>() : nullptr;
    }
    std::string geometryHash(const CpuMeshView& mesh)
    {
        uint64_t hash = 14695981039346656037ull;
        auto byte = [&](uint8_t value)
        {
            hash = (hash ^ value) * 1099511628211ull;
        };
        for (const auto* values : {&mesh.positions, &mesh.normals})
            for (const auto& row : *values)
                for (float value : row)
                {
                    uint32_t bits = std::bit_cast<uint32_t>(value);
                    for (unsigned i = 0; i < 4; ++i)
                        byte((bits >> (i * 8)) & 255);
                }
        for (uint16_t value : mesh.indices)
        {
            byte(value & 255);
            byte(value >> 8);
        }
        return std::to_string(hash);
    }
    class FrameObserver final : public render::ISceneFrameObserver,
                                public IRttiObject
    {
        NAU_RTTI_CLASS(FrameObserver, render::ISceneFrameObserver, IRttiObject)
        void frameSubmitted(const render::SceneFrame& frame) override
        {
            ++frames;
#ifdef __EMSCRIPTEN__
            MAIN_THREAD_EM_ASM({ Module.renderSubmittedFrames = $0; }, frames);
#endif
            if (stage == "frozen" && mode == "billboard-share" && frame.billboards.size() != 2)
                return;
            if (stage == "frozen" && (mode == "billboard-swap" || mode == "replace-texture") && (frame.billboards.empty() || !frame.billboards.front().texture.ends_with("666666666694")))
                return;
            if (records.isMember(stage))
                return;
            Json::Value record;
            record["draws"] = Json::Value{Json::arrayValue};
            record["updates"] = updates;
            record["camera"] = frame.camera;
            record["drawable"] = array(frame.drawable);
            record["viewProjection"] = array(frame.viewProjection);
            record["ownerThread"] = getApplication().isMainThread();
            bool valid = !motionPending;
            auto camera = getServiceProvider().get<scene::ICameraManager>().getCameras().getWorldMainCamera();
            valid = valid && camera && frame.camera == toString(camera->getCameraUid());
            auto& manager = getServiceProvider().get<scene::ISceneManagerInternal>();
            for (const auto& draw : frame.draws)
            {
                Json::Value value;
                value["component"] = draw.component;
                value["geometry"] = draw.geometry;
                value["model"] = array(draw.model);
                value["normals"] = array(draw.normals);
                value["color"] = array(draw.color);
                value["vertices"] = unsigned(draw.mesh->positions.size());
                value["indices"] = unsigned(draw.mesh->indices.size());
                value["geometryHash"] = geometryHash(*draw.mesh);
                auto uid = Uid::parseString(draw.component.c_str());
                auto* component = uid ? manager.findComponent(*uid) : nullptr;
                auto* mesh = component ? component->as<scene::StaticMeshComponent*>() : nullptr;
                valid = valid && mesh && mesh->getVisibility() && toString(mesh->getMeshGeometry()) == draw.geometry;
                if (mesh)
                {
                    value["object"] = std::string(mesh->getParentObject().getName());
                    const auto actual = copyMatrix(mesh->getWorldTransform().getMatrix());
                    for (unsigned i = 0; i < 16; ++i)
                        valid = valid && std::abs(actual[i] - draw.model[i]) < 1e-5f;
                }
                record["draws"].append(value);
            }
            record["billboards"] = Json::Value{Json::arrayValue};
            for (const auto& draw : frame.billboards)
            {
                Json::Value value;
                value["component"] = draw.component;
                value["texture"] = draw.texture;
                value["position"] = array(draw.position);
                value["size"] = draw.size;
                value["width"] = draw.image->width;
                value["height"] = draw.image->height;
                uint64_t hash = 14695981039346656037ull;
                for (auto byte : draw.image->pixels)
                    hash = (hash ^ std::to_integer<unsigned char>(byte)) * 1099511628211ull;
                value["pixelHash"] = std::to_string(hash);
                auto uid = Uid::parseString(draw.component.c_str());
                auto* component = uid ? manager.findComponent(*uid) : nullptr;
                auto* billboard = component ? component->as<scene::BillboardComponent*>() : nullptr;
                valid = valid && billboard && billboard->getVisibility() && toString(billboard->getTextureRef()) == draw.texture;
                record["billboards"].append(value);
            }
            for (auto active : getServiceProvider().get<scene::ISceneManager>().getActiveScenes())
            {
                if (!active)
                    continue;
                auto nodes = active->getRoot().getAllChildObjects();
                nodes.insert(nodes.begin(), &active->getRoot());
                for (auto* node : nodes)
                {
                    Json::Value value;
                    value["uid"] = toString(node->getUid());
                    value["name"] = std::string(node->getName());
                    value["world"] = array(copyMatrix(node->getWorldTransform().getMatrix()));
                    record["objects"].append(value);
                }
            }
            record["valid"] = valid;
            records[stage] = record;
            publish(records);
        }
    };
    class DelayedGeometry final : public IAssetContainerLoader
    {
        NAU_INTERFACE(DelayedGeometry, IAssetContainerLoader)
    public:
        std::vector<std::string_view> getSupportedAssetKind() const override
        {
            return {"probe-delayed-gltf"};
        }
        RuntimeReadonlyDictionary::Ptr getDefaultImportSettings() const override
        {
            return nullptr;
        }
        async::Task<IAssetContainer::Ptr> loadFromStream(io::IStreamReader::Ptr stream, AssetContentInfo info) override
        {
            loadAccepted = true;
            std::puts("RENDER_LOAD_ACCEPTED");
#ifdef __EMSCRIPTEN__
            MAIN_THREAD_EM_ASM({ Module.renderLoadAccepted = true; });
#endif
            if (mode == "stop-load")
            {
                getApplication().stop();
                getApplication().stop();
            }
            if (mode == "remove-load")
            {
                co_await std::chrono::milliseconds(10);
                co_await getApplication().getExecutor();
                for (auto name : {"BlueCube", "BlueRepeated"})
                    if (auto* target = object(name))
                        target->destroy();
            }
            co_await std::chrono::milliseconds(150);
            CpuMeshContainerLoader loader;
            auto loaded = co_await loader.loadFromStream(std::move(stream), std::move(info));
            loadSettled = true;
            std::puts("RENDER_LOAD_SETTLED");
#ifdef __EMSCRIPTEN__
            MAIN_THREAD_EM_ASM({ Module.renderLoadSettled = true; });
#endif
            co_return loaded;
        }
    };
    class DelayedTexture final : public IAssetContainerLoader
    {
        NAU_INTERFACE(DelayedTexture, IAssetContainerLoader)
    public:
        std::vector<std::string_view> getSupportedAssetKind() const override
        {
            return {"probe-delayed-ntex"};
        }
        RuntimeReadonlyDictionary::Ptr getDefaultImportSettings() const override
        {
            return nullptr;
        }
        async::Task<IAssetContainer::Ptr> loadFromStream(io::IStreamReader::Ptr stream, AssetContentInfo info) override
        {
            loadAccepted = true;
            std::puts("RENDER_LOAD_ACCEPTED");
            if (mode == "stop-texture")
            {
                getApplication().stop();
                getApplication().stop();
            }
            co_await std::chrono::milliseconds(100);
            co_await getApplication().getExecutor();
            if (mode == "remove-texture" && marker())
                marker()->getParentObject().removeComponent(*marker());
            if (mode == "replace-texture" && marker())
                marker()->setTextureRef(TextureAssetRef{"uid:22222222-3333-4444-5555-666666666694"});
            CpuTextureContainerLoader loader;
            auto loaded = co_await loader.loadFromStream(std::move(stream), std::move(info));
            loadSettled = true;
            std::puts("RENDER_LOAD_SETTLED");
            co_return loaded;
        }
    };
    class FaultBackend final : public render::SceneBackend
    {
    public:
        Result<> initialize(void* window) override
        {
#ifdef __EMSCRIPTEN__
            if (mode == "shader-error")
                return m_badShader.initializeBatch("this is invalid GLSL", "this is invalid GLSL");
#endif
            auto initialized = m_actual->initialize(window);
            if (!initialized)
                return initialized;
            if (mode == "init-error")
                return NauMakeError("Probe injected graphics initialization failure");
            return {};
        }
        Result<render::SceneDrawable> poll() override
        {
            if (mode == "context-loss" && !m_lost && m_submissions >= 2 && getApplication().as<ApplicationLifecycle&>().getPhase() == ApplicationPhase::Running)
            {
                m_lost = true;
#ifdef __EMSCRIPTEN__
                EM_ASM({ GL.currentContext.GLctx.getExtension('WEBGL_lose_context').loseContext(); });
#else
                return NauMakeError("Probe injected native device loss");
#endif
            }
            return m_actual->poll();
        }
        Result<> submit(const render::SceneFrame& frame) override
        {
            if (mode == "stop-upload" && !frame.draws.empty())
            {
                auto partial = frame;
                partial.draws.resize(1);
                NauCheckResult(m_actual->submit(partial));
                getApplication().stop();
                getApplication().stop();
                return {};
            }
            if (mode == "upload-error" && !frame.draws.empty())
            {
                auto partial = frame;
                partial.draws.resize(1);
                NauCheckResult(m_actual->submit(partial));
                return NauMakeError("Probe injected upload failure after accepted first-mesh work");
            }
            NauCheckResult(m_actual->submit(frame));
            ++m_submissions;
            if (mode == "submit-error")
                return NauMakeError("Probe injected submission failure");
            return {};
        }
        Result<> stop() override
        {
#ifdef __EMSCRIPTEN__
            if (mode == "shader-error")
                return m_badShader.stop();
#endif
            return m_actual->stop();
        }

    private:
        std::unique_ptr<render::SceneBackend> m_actual = render::createSceneBackend();
        unsigned m_submissions = 0;
        bool m_lost = false;
#ifdef __EMSCRIPTEN__
        BrowserRenderer m_badShader;
#endif
    };
    class FaultFactory final : public render::ISceneBackendFactory,
                               public IRttiObject
    {
        NAU_RTTI_CLASS(FaultFactory, render::ISceneBackendFactory, IRttiObject)
        std::unique_ptr<render::SceneBackend> createBackend() override
        {
            return std::make_unique<FaultBackend>();
        }
    };
    class Probe final : public ApplicationDelegate
    {
    public:
        explicit Probe(Ptr application) :
            m_application(std::move(application))
        {
        }
        ~Probe()
        {
            Json::Value result;
            result["cleanup"] = !applicationExists() && !hasServiceProvider();
            result["frames"] = frames;
            result["updates"] = updates;
            result["loadAccepted"] = loadAccepted;
            result["loadSettled"] = loadSettled;
            auto text = encode(result);
            std::printf("RENDER_CLEANUP %s\n", text.c_str());
#ifdef __EMSCRIPTEN__
            MAIN_THREAD_EM_ASM({ Module.renderCleanup = JSON.parse(UTF8ToString($0)); }, text.c_str());
#endif
        }

    private:
        Result<> configureApplication() override
        {
            return m_application->configureApplication();
        }
        std::string getModulesListString() const override
        {
            return m_application->getModulesListString();
        }
        Result<> initializeServices() override
        {
            NauCheckResult(m_application->initializeServices());
            getServiceProvider().addService(std::make_unique<FrameObserver>());
            getServiceProvider().addService(std::make_unique<DelayedGeometry>());
            getServiceProvider().addService(std::make_unique<DelayedTexture>());
            getServiceProvider().addClass<PendingMotion>();
            if (mode.ends_with("error") || mode == "context-loss" || mode == "stop-upload")
                getServiceProvider().addService(std::make_unique<FaultFactory>());
            return {};
        }
        void onApplicationInitialized() override
        {
            m_application->onApplicationInitialized();
        }
        async::Task<> startupApplication() override
        {
            co_await m_application->startupApplication();
            if (getApplication().isClosing())
                co_return;
            auto& world = getServiceProvider().get<scene::ISceneManager>().getDefaultWorld();
            world.setSimulationPause(true);
            stage = "frozen";
            {
                auto source = getServiceProvider().get<scene::ISceneFactory>().createSceneObject<scene::BillboardComponent>();
                auto& component = source->getRootComponent<scene::BillboardComponent>();
                if (std::abs(component.getScreenPercentageSize() - .1f) > 1e-6 || component.isTextureDirty() || !component.getVisibility())
                    co_await async::Task<>::makeRejected(NauMakeError("Billboard default contract failed"));
                component.setScreenPercentageSize(.25f);
                component.setVisibility(false);
                component.setTextureRef(TextureAssetRef{"uid:22222222-3333-4444-5555-666666666690"});
                std::string json;
                io::InplaceStringWriter<char> writer{json};
                co_await serialization::jsonWrite(writer, nau::Ptr{component.as<RuntimeValue*>()}, serialization::JsonSettings{});
                auto target = getServiceProvider().get<scene::ISceneFactory>().createSceneObject<scene::BillboardComponent>();
                auto parsed = serialization::jsonParseString(json);
                if (!parsed)
                    co_await async::Task<>::makeRejected(parsed.getError());
                auto& restored = target->getRootComponent<scene::BillboardComponent>();
                co_await RuntimeValue::assign(nau::Ptr{restored.as<RuntimeValue*>()}, *parsed);
                if (restored.getScreenPercentageSize() != .25f || restored.getVisibility() || toString(restored.getTextureRef()) != toString(component.getTextureRef()))
                    co_await async::Task<>::makeRejected(NauMakeError("Billboard serialization contract failed"));
                std::puts("BILLBOARD_COMPONENT_CONTRACT_PASS");
            }
            if (mode == "billboard-distance")
                marker()->setTranslation({3.6f, 2.8f, -12});
            if (mode == "billboard-swap")
                marker()->setTextureRef(TextureAssetRef{"uid:22222222-3333-4444-5555-666666666694"});
            if (mode == "billboard-parent" || mode == "billboard-share" || mode == "billboard-swap" || mode == "replace-texture")
            {
                auto parent = getServiceProvider().get<scene::ISceneFactory>().createSceneObject();
                parent->setTransform(math::Transform{math::Quat::rotationZ(.5f), math::Vector3(1, .5f, -8), math::Vector3(2, 3, 1)});
                auto child = getServiceProvider().get<scene::ISceneFactory>().createSceneObject<scene::BillboardComponent>();
                child->setTranslation({.2f, .3f, 0});
                child->getRootComponent<scene::BillboardComponent>().setTextureRef(marker()->getTextureRef());
                child->getRootComponent<scene::BillboardComponent>().setScreenPercentageSize(.12f);
                parent->attachChild(std::move(child));
                marker()->setVisibility(false);
                co_await getServiceProvider().get<scene::ISceneManager>().getActiveScenes().front()->getRoot().attachChildAsync(std::move(parent));
            }
            if (mode == "billboard-hidden")
                marker()->setVisibility(false);
            if (mode == "billboard-remove")
                marker()->getParentObject().removeComponent(*marker());
            if (mode == "billboard-behind")
                marker()->setTranslation({0, 0, 1});
            if (mode == "billboard-near")
                marker()->setTranslation({0, 0, -.01f});
            if (mode == "billboard-far")
                marker()->setTranslation({0, 0, -200});
            if (mode == "billboard-depth")
                marker()->setTranslation({-1, 0, -9});
            if (mode == "billboard-front")
                marker()->setTranslation({-1, 0, -4});
            if (mode == "billboard-edge")
                marker()->setTranslation({5.2f, 0, -6});
            if (mode == "billboard-only" || mode == "billboard-distance" || mode == "billboard-fov" || mode == "billboard-facing" || mode == "billboard-parent" || mode == "billboard-share" || mode == "billboard-swap" || mode == "replace-texture")
                for (auto name : {"BlueCube", "BlueRepeated", "OrangeTetra"})
                    object(name)->getRootComponent<scene::StaticMeshComponent>().setVisibility(false);
            if (mode == "billboard-share")
            {
                auto added = getServiceProvider().get<scene::ISceneFactory>().createSceneObject<scene::BillboardComponent>();
                auto& billboard = added->getRootComponent<scene::BillboardComponent>();
                billboard.setTextureRef(marker()->getTextureRef());
                billboard.setScreenPercentageSize(.08f);
                added->setTranslation({-2, 1.4f, -6});
                co_await getServiceProvider().get<scene::ISceneManager>().getActiveScenes().front()->getRoot().attachChildAsync(std::move(added));
            }
            if (mode == "visibility")
                object("BlueRepeated")->getRootComponent<scene::StaticMeshComponent>().setVisibility(false);
            if (mode == "removal")
                object("OrangeTetra")->destroy();
            if (mode == "empty")
            {
                marker()->setVisibility(false);
                for (auto name : {"BlueCube", "BlueRepeated", "OrangeTetra"})
                    object(name)->getRootComponent<scene::StaticMeshComponent>().setVisibility(false);
            }
            if (mode == "component-offset")
            {
                auto* parent = object("BlueRepeated");
                auto geometry = parent->getRootComponent<scene::StaticMeshComponent>().getMeshGeometry();
                auto material = parent->getRootComponent<scene::StaticMeshComponent>().getMaterial();
                co_await parent->addComponentAsync(rtti::getTypeInfo<scene::StaticMeshComponent>(), [&](scene::Component& component)
                {
                    auto& mesh = component.as<scene::StaticMeshComponent&>();
                    mesh.setMeshGeometry(geometry);
                    mesh.setMaterial(material);
                    mesh.setTransform(math::Transform{math::Quat::identity(), math::Vector3(0, 3, 0)});
                });
            }
            if (mode == "camera" || mode == "billboard-fov" || mode == "billboard-facing")
            {
                m_camera = getServiceProvider().get<scene::ICameraManager>().createDetachedCamera();
                m_camera->setTransform(math::Transform{mode == "billboard-facing" ? math::Quat::rotationY(.15f) : math::Quat::identity(), math::Vector3(0, 0, mode == "camera" ? 2 : 0)});
                m_camera->setFov(50);
                getServiceProvider().get<scene::ICameraManager>().setMainCamera(*m_camera);
            }
            if (mode == "activation")
            {
                auto object = getServiceProvider().get<scene::ISceneFactory>().createSceneObject<scene::StaticMeshComponent>();
                object->setName("AddedMesh");
                auto& mesh = object->getRootComponent<scene::StaticMeshComponent>();
                mesh.setMeshGeometry(StaticMeshAssetRef{"uid:22222222-3333-4444-5555-666666666674+[mesh/0]"});
                mesh.setMaterial(MaterialAssetRef{"uid:22222222-3333-4444-5555-666666666662"});
                object->setTransform(math::Transform{math::Quat::identity(), math::Vector3(2, 1, -8)});
                auto scene = getServiceProvider().get<scene::ISceneManager>().getActiveScenes().front();
                co_await scene->getRoot().attachChildAsync(std::move(object));
            }
            if (mode == "async-motion")
                co_await object("BlueCube")->addComponentAsync(rtti::getTypeInfo<PendingMotion>());
            co_await getServiceProvider().get<scene::IPackagedScenePresenter>().presentFrame();
            if (mode == "normal" || mode == "async-motion")
                world.setSimulationPause(false);
            else
                frozen = true;
        }
        void onApplicationPreUpdate(std::chrono::milliseconds elapsed) override
        {
            if (!frozen)
                ++updates;
            m_application->onApplicationPreUpdate(elapsed);
        }
        void onApplicationPostUpdate(std::chrono::milliseconds elapsed) override
        {
            if (!frozen && updates == 10)
                stage = "updated";
            m_application->onApplicationPostUpdate(elapsed);
            if (!frozen && updates == 10)
            {
                getServiceProvider().get<scene::ISceneManager>().getDefaultWorld().setSimulationPause(true);
                frozen = true;
            }
            if (frozen && !m_readyReported && records.isMember("frozen"))
            {
                m_readyReported = true;
                std::puts("RENDER_PROBE_READY");
                std::fflush(stdout);
#ifdef __EMSCRIPTEN__
                MAIN_THREAD_EM_ASM({ Module.renderProbeReady = true; });
#endif
            }
        }
        Ptr m_application;
        bool m_readyReported = false;
        nau::Ptr<scene::ICameraControl> m_camera;
    };
}  // namespace
int main(int argc, char** argv)
{
    if (argc > 1)
        mode = argv[1];
    scene::PackagedSceneOptions options;
    options.configurationPath = argc > 2 ? argv[2] : nau::project::StartupConfiguration;
    if (argc > 3)
        options.archivePath = argv[3];
    options.supportedComponents = nau::project::SupportedComponents;
    options.runtimeProfile = nau::project::RuntimeProfile;
    options.renderingConfiguration = nau::project::RenderingConfiguration;
    return runApplication(std::make_unique<Probe>(scene::createPackagedSceneApplication(std::move(options))));
}
