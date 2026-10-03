// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#include <gtest/gtest.h>

#include <memory>
#include <thread>

#include "nau/app/application_lifecycle.h"
#include "nau/app/application_services.h"
#include "nau/module/module_manager.h"
#include "nau/scene/components/component_life_cycle.h"
#include "nau/scene/scene_factory.h"
#include "nau/scene/scene_manager.h"
#include "nau/service/service.h"
#include "nau/service/service_provider.h"

namespace nau::test
{
    struct DemoLifecycleState
    {
        bool pending = false;
        bool pendingActivation = false;
        int activated = 0, updates = 0, asyncUpdates = 0, completed = 0, deactivated = 0, destroyed = 0;
        async::TaskSource<> release;
        async::TaskSource<> releaseActivation;
    };

    class DemoLifecycleComponent final : public scene::SceneComponent,
                                         public scene::IComponentActivation,
                                         public scene::IComponentUpdate,
                                         public scene::IComponentAsyncUpdate
    {
        NAU_OBJECT(DemoLifecycleComponent, scene::SceneComponent, scene::IComponentActivation, scene::IComponentUpdate, scene::IComponentAsyncUpdate)
        NAU_DECLARE_DYNAMIC_OBJECT
    public:
        DemoLifecycleState* state = nullptr;
        ~DemoLifecycleComponent()
        {
            if (state)
                ++state->destroyed;
        }
        void activateComponent() override
        {
            ++state->activated;
        }
        async::Task<> activateComponentAsync() override
        {
            if (state->pendingActivation)
                co_await state->releaseActivation.getTask();
        }
        void deactivateComponent() override
        {
            ++state->deactivated;
        }
        void updateComponent(float) override
        {
            ++state->updates;
        }
        async::Task<> updateComponentAsync(float) override
        {
            ++state->asyncUpdates;
            if (state->pending)
                co_await state->release.getTask();
            ++state->completed;
        }
    };
    NAU_IMPLEMENT_DYNAMIC_OBJECT(DemoLifecycleComponent)

    class DemoSceneStartup final : public IServiceInitialization
    {
        NAU_RTTI_CLASS(DemoSceneStartup, IServiceInitialization)
    public:
        explicit DemoSceneStartup(DemoLifecycleState& state) :
            state(state)
        {
        }
        async::Task<> initService() override
        {
            auto& factory = getServiceProvider().get<scene::ISceneFactory>();
            auto scene = factory.createEmptyScene();
            auto& object = scene->getRoot().attachChild(factory.createSceneObject<DemoLifecycleComponent>());
            object.getRootComponent<DemoLifecycleComponent>().state = &state;
            co_await getServiceProvider().get<scene::ISceneManager>().activateScene(std::move(scene));
        }

    private:
        DemoLifecycleState& state;
    };

    class DemoLifecycleDelegate final : public ApplicationInitDelegate
    {
    public:
        explicit DemoLifecycleDelegate(DemoLifecycleState& state) :
            state(state)
        {
        }
        Result<> configureApplication() override
        {
            return ResultSuccess;
        }
        Result<> initializeApplication() override
        {
            NauCheckResult(loadModulesList(NAU_MODULES_LIST));
            getServiceProvider().addClass<DemoLifecycleComponent>();
            getServiceProvider().addService(std::make_unique<DemoSceneStartup>(state));
            return ResultSuccess;
        }

    private:
        DemoLifecycleState& state;
    };

    static void runSceneLifecycle(bool pending)
    {
        DemoLifecycleState state;
        state.pending = pending;
        DemoLifecycleDelegate delegate(state);
        auto created = createApplicationChecked(delegate);
        ASSERT_TRUE(created);
        auto app = *std::move(created);
        auto& lifecycle = app->as<ApplicationLifecycle&>();
        lifecycle.beginStartup();
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
        while (lifecycle.getPhase() != ApplicationPhase::Running && std::chrono::steady_clock::now() < deadline)
        {
            lifecycle.pollLifecycle();
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        ASSERT_EQ(lifecycle.getPhase(), ApplicationPhase::Running);
        EXPECT_FALSE(lifecycle.getLifecycleError());
        EXPECT_EQ(state.activated, 1);
        EXPECT_EQ(state.updates, 0);
        EXPECT_TRUE(lifecycle.stepWithElapsedTime(std::chrono::milliseconds(100)));
        EXPECT_TRUE(lifecycle.stepWithElapsedTime(std::chrono::milliseconds(100)));
        EXPECT_EQ(state.updates, 2);
        EXPECT_EQ(state.asyncUpdates, pending ? 1 : 2);
        app->stop();
        app->stop();
        EXPECT_FALSE(lifecycle.stepWithElapsedTime(std::chrono::milliseconds(100)));
        for (int i = 0; i < 5; ++i)
            lifecycle.pollLifecycle();
        if (pending)
        {
            EXPECT_EQ(lifecycle.getPhase(), ApplicationPhase::Stopping);
            EXPECT_EQ(state.deactivated, 1);
            EXPECT_EQ(state.destroyed, 0);
            state.release.resolve();
        }
        deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
        while (lifecycle.getPhase() != ApplicationPhase::Stopped && std::chrono::steady_clock::now() < deadline)
        {
            lifecycle.pollLifecycle();
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        EXPECT_EQ(lifecycle.getPhase(), ApplicationPhase::Stopped);
        EXPECT_FALSE(lifecycle.getLifecycleError());
        EXPECT_EQ(state.updates, 2);
        EXPECT_EQ(state.completed, pending ? 1 : 2);
        EXPECT_EQ(state.deactivated, 1);
        EXPECT_EQ(state.destroyed, 1);
        app.reset();
        EXPECT_FALSE(applicationExists());
    }

    TEST(DemoSceneLifecycle, NormalStop)
    {
        runSceneLifecycle(false);
    }
    TEST(DemoSceneLifecycle, StopWaitsForPendingComponentWork)
    {
        runSceneLifecycle(true);
    }
    TEST(DemoSceneLifecycle, StopDuringSceneActivationCleansUpBeforeStopped)
    {
        DemoLifecycleState state;
        state.pendingActivation = true;
        DemoLifecycleDelegate delegate(state);
        auto created = createApplicationChecked(delegate);
        ASSERT_TRUE(created);
        auto app = *std::move(created);
        auto& lifecycle = app->as<ApplicationLifecycle&>();
        lifecycle.beginStartup();
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
        while (!state.activated && std::chrono::steady_clock::now() < deadline)
        {
            lifecycle.pollLifecycle();
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        EXPECT_EQ(state.activated, 1);
        EXPECT_EQ(lifecycle.getPhase(), ApplicationPhase::Initializing);
        app->stop();
        for (int i = 0; i < 5; ++i)
            lifecycle.pollLifecycle();
        EXPECT_NE(lifecycle.getPhase(), ApplicationPhase::Stopped);
        EXPECT_EQ(state.destroyed, 0);
        state.releaseActivation.resolve();
        deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
        while (lifecycle.getPhase() != ApplicationPhase::Stopped && std::chrono::steady_clock::now() < deadline)
        {
            lifecycle.pollLifecycle();
            EXPECT_NE(lifecycle.getPhase(), ApplicationPhase::Running);
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        EXPECT_EQ(lifecycle.getPhase(), ApplicationPhase::Stopped);
        EXPECT_FALSE(lifecycle.getLifecycleError());
        EXPECT_EQ(state.updates, 0);
        EXPECT_EQ(state.deactivated, 1);
        EXPECT_EQ(state.destroyed, 1);
        app.reset();
    }
}  // namespace nau::test
