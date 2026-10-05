#pragma once
#include "demo_scene.h"
#include "nau/async/task_base.h"
#include "nau/rtti/rtti_object.h"

namespace nau::demo
{
    // Private demo content/presentation integration, selected by the build.
    class DemoPlatform : public virtual IRttiObject
    {
        NAU_INTERFACE(DemoPlatform, IRttiObject)
    public:
        virtual Result<> configure() = 0;
        virtual void initialized() = 0;
        virtual async::Task<> prepareAssets() = 0;
        virtual void decorateScene(scene::IScene&, CubeScene&) = 0;
        virtual async::Task<> presentStartup(CubeScene&) = 0;
        virtual Result<> present(CubeScene&) = 0;
        virtual void observeStep(const CubeScene&, std::chrono::milliseconds)
        {
        }
        virtual void reportFailure(Error::Ptr)
        {
        }
    };
    std::unique_ptr<DemoPlatform> createDemoPlatform();
    bool demoFailed();
}  // namespace nau::demo
