// Copyright 2026 N-GINN LLC. All rights reserved.
// Use of this source code is governed by a BSD-3 Clause license that can be found in the LICENSE file.
#pragma once
#include "nau/scene/components/component.h"
#include "nau/scene/components/component_life_cycle.h"
#ifndef NAU_DEMO_PORTABLE_VECTORS
class DemoBattlezone final : public nau::scene::Component
{
    NAU_OBJECT(DemoBattlezone, nau::scene::Component)
    NAU_DECLARE_DYNAMIC_OBJECT
    NAU_CLASS_FIELDS(CLASS_NAMED_FIELD(m_content, "gameContent"))
    std::string m_content = "/content/game/battlezone.json";
};
#else
    #include <map>

    #include "battlezone_simulation.h"
    #include "nau/audio/portable_audio.h"
    #include "nau/render/scene_backend.h"

class DemoBattlezone final : public nau::scene::Component,
                             public nau::scene::IComponentUpdate,
                             public nau::scene::IComponentActivation,
                             public nau::render::ISceneVectorSource
{
    NAU_OBJECT(DemoBattlezone, nau::scene::Component, nau::scene::IComponentUpdate, nau::scene::IComponentActivation, nau::render::ISceneVectorSource)
    NAU_DECLARE_DYNAMIC_OBJECT
    NAU_CLASS_FIELDS(CLASS_NAMED_FIELD(m_content, "gameContent"))
public:
    nau::async::Task<> activateComponentAsync() override;
    void deactivateComponent() override;
    void updateComponent(float dt) override;
    nau::Result<nau::render::VectorPresentation> vectorPresentation() const override;
    const demo::battlezone::Simulation& simulation() const
    {
        return m_game;
    }
    demo::battlezone::Simulation& acceptanceState()
    {
        return m_game;
    }

private:
    struct Shape
    {
        std::vector<std::array<float, 3> > vertices;
        std::vector<std::array<unsigned, 2> > edges;
    };
    std::string m_content = "/content/game/battlezone.json";
    std::map<std::string, Shape> m_shapes;
    demo::battlezone::Simulation m_game;
    nau::audio::Clip m_fire, m_explosion;
    float m_artTime = 0, m_treadPhase = 0;
    unsigned m_epoch = 0;
    bool m_active = false;
};
#endif
