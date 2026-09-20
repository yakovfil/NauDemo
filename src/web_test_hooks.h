// Included only by the explicitly enabled browser acceptance fixture build.
#pragma once
#include "nau/scene/components/component_life_cycle.h"

namespace nau::demo::test
{
    struct PendingState
    {
        async::TaskSource<> release;
        bool pending = false, released = false;
        int deactivated = 0, destroyed = 0;
    };

    class PendingComponent final : public scene::SceneComponent,
                                   public scene::IComponentActivation,
                                   public scene::IComponentAsyncUpdate
    {
        NAU_OBJECT(PendingComponent, scene::SceneComponent, scene::IComponentActivation, scene::IComponentAsyncUpdate)
        NAU_DECLARE_DYNAMIC_OBJECT
    public:
        PendingState* state = nullptr;
        ~PendingComponent()
        {
            if (state)
                ++state->destroyed;
        }
        void activateComponent() override
        {
        }
        void deactivateComponent() override
        {
            ++state->deactivated;
        }
        async::Task<> updateComponentAsync(float) override
        {
            if (!state->released)
            {
                state->pending = true;
                co_await state->release.getTask();
                state->pending = false;
            }
        }
    };
    NAU_IMPLEMENT_DYNAMIC_OBJECT(PendingComponent)
}  // namespace nau::demo::test
