#include <gtest/gtest.h>

#include <map>
#include <string>
#include <string_view>
#include <vector>

#include "asset_manager_impl.h"
#include "demo_scene.h"
#include "nau/assets/asset_path.h"
#include "nau/diag/logging.h"
#include "nau/messaging/messaging.h"
#include "nau/scene/components/camera_component.h"
#include "nau/scene/components/static_mesh_component.h"
#include "nau/scene/scene_factory.h"
#include "nau/serialization/runtime_value_builder.h"
#include "nau/service/service_provider.h"
#include "scene_management/scene_factory_impl.h"
#include "scene_management/scene_manager_impl.h"

namespace nau::test
{
    class TrackedContainer final : public IAssetContainer
    {
        NAU_CLASS_(nau::test::TrackedContainer, IAssetContainer)
    public:
        explicit TrackedContainer(bool& destroyed) :
            m_destroyed(destroyed)
        {
        }
        ~TrackedContainer() override
        {
            m_destroyed = true;
        }
        nau::Ptr<> getAsset(std::string_view) override
        {
            return nullptr;
        }
        std::vector<std::string> getContent() const override
        {
            return {};
        }

    private:
        bool& m_destroyed;
    };

    class DemoSceneCpu : public testing::Test
    {
        void SetUp() override
        {
            diag::setLogger(diag::createLogger());
            setDefaultServiceProvider(createServiceProvider());
            auto& services = getServiceProvider();
            services.addService(AsyncMessageSource::create());
            services.addService<scene::SceneFactoryImpl>();
            services.addService<scene::SceneManagerImpl>();
            services.addClass<scene::StaticMeshComponent>();
            services.addClass<scene::CameraComponent>();
        }

        void TearDown() override
        {
            setDefaultServiceProvider(nullptr);
            diag::setLogger(nullptr);
        }
    };

    TEST_F(DemoSceneCpu, SharedDemoRotatesNinetyDegreesInTwoSeconds)
    {
        getServiceProvider().addService<AssetManagerImpl>();
        auto& factory = getServiceProvider().get<scene::ISceneFactory>();
        auto scene = factory.createEmptyScene();
        auto demo = demo::createCubeScene(factory, *scene);
        const float initial = demo.angle;
        for (int step = 0; step < 20; ++step)
            demo.advance(std::chrono::milliseconds(100));
        EXPECT_NEAR(demo.angle - initial, 1.570796327f, 1e-5f);
        auto rotation = demo.cube->getWorldTransform().getRotation();
        // Orientation is independent of the native approximate normalizer length.
        EXPECT_NEAR(2 * std::atan2(float(rotation.getY()), float(rotation.getW())), demo.angle, 1e-5f);
        EXPECT_FLOAT_EQ(float(demo.camera->getWorldTransform().getTranslation().getZ()), 9);
        EXPECT_FLOAT_EQ(demo.camera->getRootComponent<scene::CameraComponent>().getFov(), 45);
    }

    TEST_F(DemoSceneCpu, SceneOwnsObjectsAndInvalidatesWeakReferences)
    {
        auto& factory = getServiceProvider().get<scene::ISceneFactory>();
        scene::ObjectWeakRef<scene::SceneObject> weak;
        {
            auto scene = factory.createEmptyScene();
            auto& cube = scene->getRoot().attachChild(factory.createSceneObject<scene::StaticMeshComponent>());
            weak = cube;
            EXPECT_TRUE(weak);
            EXPECT_EQ(cube.getScene(), scene.get());
            cube.setTranslation({1, 2, 3});
            EXPECT_FLOAT_EQ(float(cube.getWorldTransform().getTranslation().getY()), 2);
        }
        EXPECT_FALSE(weak);
    }

    TEST_F(DemoSceneCpu, ChildTransformAndCameraUseRealComponents)
    {
        auto& factory = getServiceProvider().get<scene::ISceneFactory>();
        auto scene = factory.createEmptyScene();
        auto& root = scene->getRoot();
        root.setTranslation({2, 3, 4});
        auto& cameraObject = root.attachChild(factory.createSceneObject<scene::CameraComponent>());
        cameraObject.setTranslation({1, 2, 3});
        EXPECT_FLOAT_EQ(float(cameraObject.getWorldTransform().getTranslation().getX()), 3);
        auto& camera = cameraObject.getRootComponent<scene::CameraComponent>();
        camera.setFov(45);
        EXPECT_FLOAT_EQ(camera.getFov(), 45);
    }

    TEST_F(DemoSceneCpu, AssetPathRetainsSubresourceAndReportsMissingManager)
    {
        AssetPath path("file:/demo/cube.gltf+[mesh/0]");
        EXPECT_TRUE(path);
        EXPECT_EQ(path.getContainerPath(), "/demo/cube.gltf");
        EXPECT_EQ(path.getAssetInnerPath(), "mesh/0");
        EXPECT_FALSE(path.resolve());
        EXPECT_FALSE(AssetPath::isValid("invalid"));
    }

    TEST_F(DemoSceneCpu, AssetManagerOwnsRegisteredContainerUntilRemoval)
    {
        getServiceProvider().addService<AssetManagerImpl>();
        auto& manager = getServiceProvider().get<AssetManagerImpl>();
        bool destroyed = false;
        AssetPath path("test:/cube");
        manager.addAssetContainer(path, rtti::createInstance<TrackedContainer>(destroyed));
        EXPECT_FALSE(destroyed);
        EXPECT_TRUE(manager.findAsset(path));
        manager.removeAssetContainer(path);
        EXPECT_FALSE(manager.findAsset(path));
        EXPECT_TRUE(destroyed);
    }

    TEST_F(DemoSceneCpu, AssetManagerReportsUnregisteredScheme)
    {
        getServiceProvider().addService<AssetManagerImpl>();
        auto& manager = getServiceProvider().get<AssetManagerImpl>();
        AssetPath path("missing:/cube.gltf");
        EXPECT_FALSE(manager.findAsset(path));
        EXPECT_FALSE(manager.resolvePath(path));
    }
    TEST_F(DemoSceneCpu, DictionaryEnumeratesStdAndEastlMapKeys)
    {
        std::map<std::string, unsigned> standard{
            {  "NORMAL", 1},
            {"POSITION", 0}
        };
        std::map<std::string, unsigned> east{
            {  "NORMAL", 1},
            {"POSITION", 0}
        };
        auto stdValue = makeValueRef(standard);
        auto eastValue = makeValueRef(east);
        ASSERT_EQ(stdValue->getSize(), 2);
        ASSERT_EQ(eastValue->getSize(), 2);
        EXPECT_EQ(stdValue->getKey(0), "NORMAL");
        EXPECT_EQ(stdValue->getKey(1), "POSITION");
        EXPECT_EQ(eastValue->getKey(0), "NORMAL");
        EXPECT_EQ(eastValue->getKey(1), "POSITION");
    }
}  // namespace nau::test
